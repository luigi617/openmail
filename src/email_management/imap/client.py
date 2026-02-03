from __future__ import annotations

import imaplib
import re
import threading
import time
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from email.message import EmailMessage as PyEmailMessage
from email.parser import BytesParser
from email.policy import default as default_policy
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from email_management import IMAPConfig
from email_management.auth import AuthContext
from email_management.errors import ConfigError, IMAPError
from email_management.imap.bodystructure import (
    extract_bodystructure_from_fetch_meta,
    extract_text_and_attachments,
    parse_bodystructure,
    pick_best_text_parts,
)
from email_management.imap.pagination import PagedSearchResult
from email_management.imap.parser import decode_body_chunk, decode_transfer, parse_headers_and_bodies, parse_overview
from email_management.imap.query import IMAPQuery
from email_management.types import EmailRef
from email_management.utils import parse_list_mailbox_name
from email_management.models import EmailMessage, EmailOverview, AttachmentMeta

UID_RE = re.compile(r"UID\s+(\d+)", re.IGNORECASE)
INTERNALDATE_RE = re.compile(r'INTERNALDATE\s+"([^"]+)"', re.IGNORECASE)
FLAGS_RE = re.compile(r"FLAGS\s*\(([^)]*)\)", re.IGNORECASE)

# Used for parsing FETCH section results
MIME_TOKEN_RE = re.compile(r"BODY\[(\d+(?:\.\d+)*)\.MIME\]", re.IGNORECASE)
BODY_TOKEN_RE = re.compile(r"BODY\[(\d+(?:\.\d+)*)\]", re.IGNORECASE)
HEADER_PEEK_RE = re.compile(r"BODY\[HEADER\]", re.IGNORECASE)


def _extract_payload_from_fetch_item(
    item: tuple, data: list, i: int
) -> Tuple[Optional[bytes], bool]:
    """
    Returns (payload_bytes, used_next_element).

    imaplib can return:
      - (meta, payload)
      - (meta, None) then payload as next bytes item
    """
    raw = item[1] if len(item) > 1 and isinstance(item[1], (bytes, bytearray)) else None
    used_next = False
    if raw is None and i + 1 < len(data) and isinstance(data[i + 1], (bytes, bytearray)):
        raw = data[i + 1]
        used_next = True
    return raw, used_next


@dataclass
class IMAPClient:
    config: IMAPConfig
    _conn: imaplib.IMAP4 | None = field(default=None, init=False, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _selected_mailbox: str | None = field(default=None, init=False, repr=False)
    _selected_readonly: bool | None = field(default=None, init=False, repr=False)

    # cache key: (mailbox, criteria_str) -> ascending UID list
    _search_cache: Dict[tuple[str, str], List[int]] = field(default_factory=dict, init=False, repr=False)

    max_retries: int = 1
    backoff_seconds: float = 0.0

    @classmethod
    def from_config(cls, config: IMAPConfig) -> "IMAPClient":
        if not config.host:
            raise ConfigError("IMAP host required")
        if not config.port:
            raise ConfigError("IMAP port required")
        return cls(config)

    # -----------------------
    # Connection management
    # -----------------------

    def _open_new_connection(self) -> imaplib.IMAP4:
        cfg = self.config
        try:
            conn = (
                imaplib.IMAP4_SSL(cfg.host, cfg.port, timeout=cfg.timeout)
                if cfg.use_ssl
                else imaplib.IMAP4(cfg.host, cfg.port, timeout=cfg.timeout)
            )

            if cfg.auth is None:
                raise ConfigError("IMAPConfig.auth is required (PasswordAuth or OAuth2Auth)")

            cfg.auth.apply_imap(conn, AuthContext(host=cfg.host, port=cfg.port))
            return conn

        except imaplib.IMAP4.error as e:
            raise IMAPError(f"IMAP connection/auth failed: {e}") from e
        except OSError as e:
            raise IMAPError(f"IMAP network error: {e}") from e

    def _get_conn(self) -> imaplib.IMAP4:
        # Must be called with self._lock held
        if self._conn is not None:
            return self._conn
        self._conn = self._open_new_connection()
        self._selected_mailbox = None
        self._selected_readonly = None
        return self._conn

    def _reset_conn(self) -> None:
        # Must be called with self._lock held
        if self._conn is not None:
            try:
                self._conn.logout()
            except Exception:
                pass
        self._conn = None
        self._selected_mailbox = None
        self._selected_readonly = None

    def _run_with_conn(self, op: Callable[[imaplib.IMAP4], object]):
        """
        Run an operation with thread-safety and reconnect-on-abort retry.
        """
        last_exc: Optional[BaseException] = None
        attempts = self.max_retries + 1

        for attempt in range(attempts):
            with self._lock:
                conn = self._get_conn()
                try:
                    return op(conn)
                except imaplib.IMAP4.abort as e:
                    last_exc = e
                    self._reset_conn()
                except imaplib.IMAP4.error as e:
                    raise IMAPError(f"IMAP operation failed: {e}") from e

            if attempt < attempts - 1 and self.backoff_seconds > 0:
                time.sleep(self.backoff_seconds)

        raise IMAPError(f"IMAP connection repeatedly aborted: {last_exc}") from last_exc

    # -----------------------
    # Mailbox selection helpers
    # -----------------------

    def _format_mailbox_arg(self, mailbox: str) -> str:
        if mailbox.upper() == "INBOX":
            return "INBOX"
        if mailbox.startswith('"') and mailbox.endswith('"'):
            return mailbox
        return f'"{mailbox}"'

    def _ensure_selected(self, conn: imaplib.IMAP4, mailbox: str, readonly: bool) -> None:
        """
        Cache selected mailbox to avoid repeated SELECT/EXAMINE.
        RW selection satisfies both RW and RO operations.
        RO selection satisfies only RO operations.
        """
        # Must be called with self._lock held.
        if self._selected_mailbox == mailbox:
            if self._selected_readonly is False:
                return  # already RW
            if readonly and self._selected_readonly is True:
                return  # already RO and RO requested

        imap_mailbox = self._format_mailbox_arg(mailbox)
        typ, _ = conn.select(imap_mailbox, readonly=readonly)
        if typ != "OK":
            raise IMAPError(f"select({mailbox!r}, readonly={readonly}) failed")

        self._selected_mailbox = mailbox
        self._selected_readonly = readonly

    def _assert_same_mailbox(self, refs: Sequence[EmailRef], op_name: str) -> str:
        if not refs:
            raise IMAPError(f"{op_name} called with empty refs")
        mailbox = refs[0].mailbox
        for r in refs:
            if r.mailbox != mailbox:
                raise IMAPError(
                    f"All EmailRef.mailbox must match for {op_name} "
                    f"(got {refs[0].mailbox!r} and {r.mailbox!r})"
                )
        return mailbox

    # -----------------------
    # Cache invalidation
    # -----------------------

    def _invalidate_search_cache(self, mailbox: Optional[str] = None) -> None:
        """
        Invalidate cached search results (simple + safe).
        If mailbox is provided, only clear entries for that mailbox.
        """
        with self._lock:
            if mailbox is None:
                self._search_cache.clear()
                return
            keys = [k for k in self._search_cache.keys() if k[0] == mailbox]
            for k in keys:
                self._search_cache.pop(k, None)

    # -----------------------
    # LIST parsing
    # -----------------------

    def _parse_list_flags(self, raw: bytes) -> Set[str]:
        try:
            s = raw.decode(errors="ignore")
        except Exception:
            return set()

        start = s.find("(")
        end = s.find(")", start + 1)
        if start == -1 or end == -1 or end <= start + 1:
            return set()

        flags_str = s[start + 1 : end].strip()
        if not flags_str:
            return set()

        return {f.upper() for f in flags_str.split() if f.strip()}

    # -----------------------
    # SEARCH + pagination
    # -----------------------

    def refresh_search_cache(self, *, mailbox: str, query: IMAPQuery) -> List[int]:
        criteria = query.build() or "ALL"
        cache_key = (mailbox, criteria)

        def _impl(conn: imaplib.IMAP4) -> List[int]:
            self._ensure_selected(conn, mailbox, readonly=True)
            typ, data = conn.uid("SEARCH", None, criteria)
            if typ != "OK":
                raise IMAPError(f"SEARCH failed: {data}")

            raw = data[0] or b""
            uids = [int(x) for x in raw.split()]

            self._search_cache[cache_key] = uids
            return uids

        return self._run_with_conn(_impl)

    def search_page_cached(
        self,
        *,
        mailbox: str,
        query: IMAPQuery,
        page_size: int = 50,
        before_uid: Optional[int] = None,
        after_uid: Optional[int] = None,
        refresh: bool = False,
    ) -> PagedSearchResult:
        if before_uid is not None and after_uid is not None:
            raise ValueError("Cannot specify both before_uid and after_uid")

        criteria = query.build() or "ALL"
        cache_key = (mailbox, criteria)

        with self._lock:
            uids = None if refresh else self._search_cache.get(cache_key)

        if uids is None:
            uids = self.refresh_search_cache(mailbox=mailbox, query=query)

        if not uids:
            return PagedSearchResult(refs=[], total=0, has_next=False, has_prev=False)

        uids_sorted = uids  # ascending old->new
        total_matches = len(uids_sorted)

        if before_uid is not None:
            idx = bisect_left(uids_sorted, before_uid)
            end = idx
            start = max(0, end - page_size)
        elif after_uid is not None:
            idx = bisect_right(uids_sorted, after_uid)
            start = idx
            end = min(len(uids_sorted), start + page_size)
        else:
            end = len(uids_sorted)
            start = max(0, end - page_size)

        if start >= end:
            return PagedSearchResult(refs=[], total=total_matches, has_next=False, has_prev=False)

        page_uids_asc = uids_sorted[start:end]
        page_uids_desc = list(reversed(page_uids_asc))

        refs = [EmailRef(uid=uid, mailbox=mailbox) for uid in page_uids_desc]

        oldest_uid = page_uids_asc[0]
        newest_uid = page_uids_asc[-1]

        has_older = start > 0
        has_newer = end < len(uids_sorted)

        return PagedSearchResult(
            refs=refs,
            next_before_uid=oldest_uid if has_older else None,
            prev_after_uid=newest_uid if has_newer else None,
            newest_uid=newest_uid,
            oldest_uid=oldest_uid,
            total=total_matches,
            has_next=has_older,
            has_prev=has_newer,
        )

    def search(self, *, mailbox: str, query: IMAPQuery, limit: int = 50) -> List[EmailRef]:
        page = self.search_page_cached(
            mailbox=mailbox,
            query=query,
            page_size=limit,
            refresh=True,
        )
        return page.refs

    # -----------------------
    # FETCH helpers
    # -----------------------

    def _fetch_section_mime_and_body(
        self, conn: imaplib.IMAP4, *, uid: int, section: str
    ) -> Tuple[Optional[bytes], Optional[bytes]]:
        want = f"(UID BODY.PEEK[{section}.MIME] BODY.PEEK[{section}])"
        typ, data = conn.uid("FETCH", str(uid), want)
        if typ != "OK":
            raise IMAPError(f"FETCH body section failed uid={uid}: {data}")

        mime_bytes: Optional[bytes] = None
        body_bytes: Optional[bytes] = None

        j = 0
        while j < len(data):
            it = data[j]
            if not isinstance(it, tuple) or not it:
                j += 1
                continue

            meta_b = it[0]
            if not isinstance(meta_b, (bytes, bytearray)):
                j += 1
                continue

            meta_s = meta_b.decode(errors="ignore")
            pay, used_n = _extract_payload_from_fetch_item(it, data, j)

            if isinstance(pay, (bytes, bytearray)):
                if MIME_TOKEN_RE.search(meta_s):
                    mime_bytes = bytes(pay)
                elif BODY_TOKEN_RE.search(meta_s) and not MIME_TOKEN_RE.search(meta_s):
                    body_bytes = bytes(pay)

            j += 2 if used_n else 1

        return mime_bytes, body_bytes

    def _decode_section(self, *, mime_bytes: Optional[bytes], body_bytes: Optional[bytes]) -> str:
        if not body_bytes:
            return ""
        if not mime_bytes:
            try:
                return body_bytes.decode("utf-8", errors="replace")
            except Exception:
                return body_bytes.decode("latin-1", errors="replace")

        msg = BytesParser(policy=default_policy).parsebytes(mime_bytes)
        return decode_body_chunk(body_bytes, msg)

    # -----------------------
    # FETCH full message (headers + best text/html via BODYSTRUCTURE)
    # -----------------------

    def fetch(self, refs: Sequence[EmailRef], *, include_attachment_meta: bool = False) -> List[EmailMessage]:
        if not refs:
            return []

        mailbox = self._assert_same_mailbox(refs, "fetch")
        required_uids = {r.uid for r in refs}

        def _impl(conn: imaplib.IMAP4) -> List[EmailMessage]:
            self._ensure_selected(conn, mailbox, readonly=True)

            uid_str = ",".join(str(r.uid) for r in refs)
            attrs = "(UID INTERNALDATE BODYSTRUCTURE BODY.PEEK[HEADER])"
            typ, data = conn.uid("FETCH", uid_str, attrs)
            if typ != "OK":
                raise IMAPError(f"FETCH failed: {data}")
            if not data:
                return []

            # Collect per-UID: headers bytes, internaldate str, bodystructure str
            partial: Dict[int, Dict[str, object]] = {}
            current_uid: Optional[int] = None

            i = 0
            n = len(data)
            while i < n:
                item = data[i]

                if isinstance(item, (bytes, bytearray)):
                    if item.strip() == b")":
                        current_uid = None
                    i += 1
                    continue

                if not isinstance(item, tuple) or not item:
                    i += 1
                    continue

                meta_raw = item[0]
                if not isinstance(meta_raw, (bytes, bytearray)):
                    i += 1
                    continue

                meta_str = meta_raw.decode(errors="ignore")
                payload, used_next = _extract_payload_from_fetch_item(item, data, i)

                m_uid = UID_RE.search(meta_str)
                if m_uid:
                    uid = int(m_uid.group(1))
                    current_uid = uid if uid in required_uids else None

                if current_uid is None:
                    i += 2 if used_next else 1
                    continue

                bucket = partial.setdefault(
                    current_uid,
                    {"headers": None, "internaldate": None, "bodystructure": None},
                )

                m_internal = INTERNALDATE_RE.search(meta_str)
                if m_internal:
                    bucket["internaldate"] = m_internal.group(1)

                if HEADER_PEEK_RE.search(meta_str) and isinstance(payload, (bytes, bytearray)):
                    bucket["headers"] = bytes(payload)

                bs = extract_bodystructure_from_fetch_meta(meta_str)
                if bs:
                    bucket["bodystructure"] = bs

                i += 2 if used_next else 1

            out: List[EmailMessage] = []
            for r in refs:
                info = partial.get(r.uid)
                if not info:
                    continue

                header_bytes = info.get("headers") or b""
                internaldate_raw = info.get("internaldate")
                bs_raw = info.get("bodystructure")

                text = ""
                html = ""
                attachment_metas: List[AttachmentMeta] = []

                if isinstance(bs_raw, str) and bs_raw:
                    try:
                        tree = parse_bodystructure(bs_raw)
                        text_parts, atts = extract_text_and_attachments(tree)
                        plain_ref, html_ref = pick_best_text_parts(text_parts)

                        if include_attachment_meta:
                            attachment_metas = atts

                        if plain_ref is not None:
                            mime_b, body_b = self._fetch_section_mime_and_body(conn, uid=r.uid, section=plain_ref.part)
                            text = self._decode_section(mime_bytes=mime_b, body_bytes=body_b)

                        if html_ref is not None:
                            mime_b, body_b = self._fetch_section_mime_and_body(conn, uid=r.uid, section=html_ref.part)
                            html = self._decode_section(mime_bytes=mime_b, body_bytes=body_b)

                    except Exception:
                        # Best-effort: headers still returned; bodies left empty.
                        pass

                msg = parse_headers_and_bodies(
                    r,
                    header_bytes,
                    text=text,
                    html=html,
                    attachments=attachment_metas if include_attachment_meta else [],
                    internaldate_raw=internaldate_raw if isinstance(internaldate_raw, str) else None,
                )
                out.append(msg)

            return out

        return self._run_with_conn(_impl)

    # -----------------------
    # FETCH overview
    # -----------------------

    def fetch_overview(self, refs: Sequence[EmailRef]) -> List[EmailOverview]:
        if not refs:
            return []
        mailbox = self._assert_same_mailbox(refs, "fetch_overview")

        def _impl(conn: imaplib.IMAP4) -> List[EmailOverview]:
            self._ensure_selected(conn, mailbox, readonly=True)

            uid_str = ",".join(str(r.uid) for r in refs)
            attrs = (
                "(UID FLAGS INTERNALDATE "
                "BODY.PEEK[HEADER.FIELDS (From To Subject Date Message-ID Content-Type Content-Transfer-Encoding)])"
            )
            typ, data = conn.uid("FETCH", uid_str, attrs)
            if typ != "OK":
                raise IMAPError(f"FETCH overview failed: {data}")
            if not data:
                return []

            partial: Dict[int, Dict[str, object]] = {}
            current_uid: Optional[int] = None
            i = 0
            n = len(data)

            while i < n:
                item = data[i]

                if isinstance(item, (bytes, bytearray)):
                    if item.strip() == b")":
                        current_uid = None
                    i += 1
                    continue

                if not isinstance(item, tuple) or not item:
                    i += 1
                    continue

                meta_raw = item[0]
                if not isinstance(meta_raw, (bytes, bytearray)):
                    i += 1
                    continue

                meta = meta_raw.decode(errors="ignore")
                payload, used_next = _extract_payload_from_fetch_item(item, data, i)

                m_uid = UID_RE.search(meta)
                if m_uid:
                    current_uid = int(m_uid.group(1))

                if current_uid is None:
                    i += 2 if used_next else 1
                    continue

                bucket = partial.setdefault(
                    current_uid,
                    {"flags": set(), "headers": None, "internaldate": None},
                )

                m_flags = FLAGS_RE.search(meta)
                if m_flags:
                    flags_str = m_flags.group(1).strip()
                    bucket["flags"] = {f for f in flags_str.split() if f} if flags_str else set()

                m_internal = INTERNALDATE_RE.search(meta)
                if m_internal:
                    bucket["internaldate"] = m_internal.group(1)

                # payload holds the header fields
                if isinstance(payload, (bytes, bytearray)):
                    bucket["headers"] = bytes(payload)

                i += 2 if used_next else 1

            overviews: List[EmailOverview] = []
            for r in refs:
                info = partial.get(r.uid)
                if not info:
                    continue

                flags = set(info["flags"]) if isinstance(info["flags"], set) else set()
                header_bytes = info.get("headers") or b""
                internaldate_raw = info.get("internaldate")

                overviews.append(
                    parse_overview(
                        r,
                        flags,
                        header_bytes,
                        internaldate_raw=internaldate_raw if isinstance(internaldate_raw, str) else None,
                    )
                )

            return overviews

        return self._run_with_conn(_impl)

    # -----------------------
    # Attachment fetch
    # -----------------------

    def fetch_attachment(self, ref: EmailRef, attachment_part: str) -> bytes:
        mailbox = ref.mailbox
        uid = ref.uid
        part = attachment_part

        def _impl(conn: imaplib.IMAP4) -> bytes:
            self._ensure_selected(conn, mailbox, readonly=True)

            typ, mime_data = conn.uid("FETCH", str(uid), f"(UID BODY.PEEK[{part}.MIME])")
            if typ != "OK" or not mime_data:
                raise IMAPError(f"FETCH attachment MIME failed uid={uid} part={part}: {mime_data}")

            mime_bytes = None
            for item in mime_data:
                if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], (bytes, bytearray)):
                    mime_bytes = bytes(item[1])
                    break

            cte = None
            if mime_bytes:
                msg = BytesParser(policy=default_policy).parsebytes(mime_bytes)
                cte = msg.get("Content-Transfer-Encoding")

            typ, body_data = conn.uid("FETCH", str(uid), f"(UID BODY.PEEK[{part}])")
            if typ != "OK" or not body_data:
                raise IMAPError(f"FETCH attachment failed uid={uid} part={part}: {body_data}")

            payload = None
            for item in body_data:
                if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], (bytes, bytearray)):
                    payload = bytes(item[1])
                    break

            if payload is None:
                raise IMAPError(f"Attachment payload not found uid={uid} part={part}")

            return decode_transfer(payload, cte)

        return self._run_with_conn(_impl)

    # -----------------------
    # Mutations
    # -----------------------

    def append(
        self,
        mailbox: str,
        msg: PyEmailMessage,
        *,
        flags: Optional[Set[str]] = None,
    ) -> EmailRef:
        def _impl(conn: imaplib.IMAP4) -> EmailRef:
            self._ensure_selected(conn, mailbox, readonly=False)

            flags_arg = "(" + " ".join(sorted(flags)) + ")" if flags else None
            date_time = imaplib.Time2Internaldate(time.time())
            raw_bytes = msg.as_bytes()
            imap_mailbox = self._format_mailbox_arg(mailbox)

            typ, data = conn.append(imap_mailbox, flags_arg, date_time, raw_bytes)
            if typ != "OK":
                raise IMAPError(f"APPEND to {mailbox!r} failed: {data}")

            uid: Optional[int] = None
            if data and data[0]:
                resp = data[0].decode(errors="ignore") if isinstance(data[0], bytes) else str(data[0])
                m = re.search(r"APPENDUID\s+\d+\s+(\d+)", resp)
                if m:
                    uid = int(m.group(1))

            if uid is None:
                typ_search, data_search = conn.uid("SEARCH", None, "ALL")
                if typ_search == "OK" and data_search and data_search[0]:
                    all_uids = [int(x) for x in data_search[0].split() if x.strip()]
                    uid = max(all_uids) if all_uids else None

            if uid is None:
                raise IMAPError("APPEND succeeded but could not determine UID")

            return EmailRef(uid=uid, mailbox=mailbox)

        ref = self._run_with_conn(_impl)  # type: ignore[assignment]
        self._invalidate_search_cache(mailbox)
        return ref

    def add_flags(self, refs: Sequence[EmailRef], *, flags: Set[str]) -> None:
        self._store(refs, mode="+FLAGS", flags=flags)

    def remove_flags(self, refs: Sequence[EmailRef], *, flags: Set[str]) -> None:
        self._store(refs, mode="-FLAGS", flags=flags)

    def _store(self, refs: Sequence[EmailRef], *, mode: str, flags: Set[str]) -> None:
        if not refs:
            return
        mailbox = self._assert_same_mailbox(refs, "_store")

        def _impl(conn: imaplib.IMAP4) -> None:
            self._ensure_selected(conn, mailbox, readonly=False)
            uids = ",".join(str(r.uid) for r in refs)
            flag_list = "(" + " ".join(sorted(flags)) + ")"
            typ, data = conn.uid("STORE", uids, mode, flag_list)
            if typ != "OK":
                raise IMAPError(f"STORE failed: {data}")

        self._run_with_conn(_impl)
        # flags can change search results depending on query criteria
        self._invalidate_search_cache(mailbox)

    def expunge(self, mailbox: str = "INBOX") -> None:
        def _impl(conn: imaplib.IMAP4) -> None:
            self._ensure_selected(conn, mailbox, readonly=False)
            typ, data = conn.expunge()
            if typ != "OK":
                raise IMAPError(f"EXPUNGE failed: {data}")

        self._run_with_conn(_impl)
        self._invalidate_search_cache(mailbox)

    # -----------------------
    # Mailboxes
    # -----------------------

    def list_mailboxes(self) -> List[str]:
        def _impl(conn: imaplib.IMAP4) -> List[str]:
            typ, data = conn.list()
            if typ != "OK":
                raise IMAPError(f"LIST failed: {data}")

            mailboxes: List[str] = []
            for raw in data or []:
                if not raw:
                    continue

                flags = self._parse_list_flags(raw)
                if r"\NOSELECT" in flags:
                    continue

                name = parse_list_mailbox_name(raw)
                if name is not None:
                    mailboxes.append(name)

            return mailboxes

        return self._run_with_conn(_impl)

    def mailbox_status(self, mailbox: str = "INBOX") -> Dict[str, int]:
        def _impl(conn: imaplib.IMAP4) -> Dict[str, int]:
            imap_mailbox = self._format_mailbox_arg(mailbox)

            typ, data = conn.status(
                imap_mailbox,
                "(MESSAGES UNSEEN UIDNEXT UIDVALIDITY HIGHESTMODSEQ)",
            )
            if typ != "OK":
                raise IMAPError(f"STATUS {mailbox!r} failed: {data}")
            if not data or not data[0]:
                raise IMAPError(f"STATUS {mailbox!r} returned empty data")

            raw = data[0]
            s = raw.decode(errors="ignore") if isinstance(raw, bytes) else str(raw)

            start = s.find("(")
            end = s.rfind(")")
            if start == -1 or end == -1 or end <= start:
                raise IMAPError(f"Unexpected STATUS response: {s!r}")

            payload = s[start + 1 : end]
            tokens = payload.split()

            status: Dict[str, int] = {}

            for i in range(0, len(tokens) - 1, 2):
                key = tokens[i].upper()
                try:
                    val = int(tokens[i + 1])
                except ValueError:
                    continue

                if key == "MESSAGES":
                    status["messages"] = val
                elif key == "UNSEEN":
                    status["unseen"] = val
                elif key == "UIDNEXT":
                    status["uidnext"] = val
                elif key == "UIDVALIDITY":
                    status["uidvalidity"] = val
                elif key == "HIGHESTMODSEQ":
                    status["highestmodseq"] = val
                else:
                    status[key.lower()] = val

            return status

        return self._run_with_conn(_impl)

    def move(self, refs: Sequence[EmailRef], *, src_mailbox: str, dst_mailbox: str) -> None:
        if not refs:
            return
        for r in refs:
            if r.mailbox != src_mailbox:
                raise IMAPError("All EmailRef.mailbox must match src_mailbox for move()")

        def _impl(conn: imaplib.IMAP4) -> None:
            self._ensure_selected(conn, src_mailbox, readonly=False)

            uids = ",".join(str(r.uid) for r in refs)
            dst_arg = self._format_mailbox_arg(dst_mailbox)

            typ, data = conn.uid("MOVE", uids, dst_arg)
            if typ == "OK":
                return

            typ_copy, data_copy = conn.uid("COPY", uids, dst_arg)
            if typ_copy != "OK":
                raise IMAPError(f"COPY (for MOVE fallback) failed: {data_copy}")

            typ_store, data_store = conn.uid("STORE", uids, "+FLAGS.SILENT", r"(\Deleted)")
            if typ_store != "OK":
                raise IMAPError(f"STORE +FLAGS.SILENT \\Deleted failed: {data_store}")

            typ_expunge, data_expunge = conn.expunge()
            if typ_expunge != "OK":
                raise IMAPError(f"EXPUNGE (after MOVE fallback) failed: {data_expunge}")

        self._run_with_conn(_impl)
        self._invalidate_search_cache(src_mailbox)
        self._invalidate_search_cache(dst_mailbox)

    def copy(self, refs: Sequence[EmailRef], *, src_mailbox: str, dst_mailbox: str) -> None:
        if not refs:
            return
        for r in refs:
            if r.mailbox != src_mailbox:
                raise IMAPError("All EmailRef.mailbox must match src_mailbox for copy()")

        def _impl(conn: imaplib.IMAP4) -> None:
            self._ensure_selected(conn, src_mailbox, readonly=False)

            uids = ",".join(str(r.uid) for r in refs)
            dst_arg = self._format_mailbox_arg(dst_mailbox)
            typ, data = conn.uid("COPY", uids, dst_arg)
            if typ != "OK":
                raise IMAPError(f"COPY failed: {data}")

        self._run_with_conn(_impl)
        self._invalidate_search_cache(dst_mailbox)

    def create_mailbox(self, name: str) -> None:
        def _impl(conn: imaplib.IMAP4) -> None:
            imap_name = self._format_mailbox_arg(name)
            typ, data = conn.create(imap_name)
            if typ != "OK":
                raise IMAPError(f"CREATE {name!r} failed: {data}")

        self._run_with_conn(_impl)
        self._invalidate_search_cache()

    def delete_mailbox(self, name: str) -> None:
        def _impl(conn: imaplib.IMAP4) -> None:
            imap_name = self._format_mailbox_arg(name)
            typ, data = conn.delete(imap_name)
            if typ != "OK":
                raise IMAPError(f"DELETE {name!r} failed: {data}")

        self._run_with_conn(_impl)
        self._invalidate_search_cache()

    def ping(self) -> None:
        def _impl(conn: imaplib.IMAP4) -> None:
            typ, data = conn.noop()
            if typ != "OK":
                raise IMAPError(f"NOOP failed: {data}")

        self._run_with_conn(_impl)

    def close(self) -> None:
        with self._lock:
            self._reset_conn()

    def __enter__(self) -> "IMAPClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
