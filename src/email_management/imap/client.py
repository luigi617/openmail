from __future__ import annotations
import imaplib
import time
import re
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Set, Dict
from email.message import EmailMessage as PyEmailMessage
from email.policy import default as default_policy

from email_management.auth import AuthContext
from email_management import IMAPConfig
from email_management.errors import ConfigError, IMAPError
from email_management.models import EmailMessage, EmailOverview
from email_management.types import EmailRef
from email_management.utils import parse_list_mailbox_name

from email_management.imap.query import IMAPQuery
from email_management.imap.parser import parse_rfc822, parse_overview
from email_management.imap.pagination import PagedSearchResult

UID_RE = re.compile(r"UID\s+(\d+)", re.IGNORECASE)
INTERNALDATE_RE = re.compile(r'INTERNALDATE\s+"([^"]+)"', re.IGNORECASE)
FLAGS_RE = re.compile(r"FLAGS\s*\(([^)]*)\)", re.IGNORECASE)
HEADER_TOKEN_RE = re.compile(r"BODY\[HEADER\.FIELDS", re.IGNORECASE)
TEXT_TOKEN_RE = re.compile(r"BODY\[TEXT]", re.IGNORECASE)

@dataclass
class IMAPClient:
    config: IMAPConfig
    _conn: imaplib.IMAP4 | None = field(default=None, init=False, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _selected_mailbox: str | None = field(default=None, init=False, repr=False)
    _selected_readonly: bool | None = field(default=None, init=False, repr=False)

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
        # NOTE: must be called with self._lock held
        if self._conn is not None:
            return self._conn
        self._conn = self._open_new_connection()
        self._selected_mailbox = None
        self._selected_readonly = None
        return self._conn

    def _reset_conn(self) -> None:
        # NOTE: must be called with self._lock held
        if self._conn is not None:
            try:
                self._conn.logout()
            except Exception:
                pass
        self._conn = None
        self._selected_mailbox = None
        self._selected_readonly = None

    def _format_mailbox_arg(self, mailbox: str) -> str:
        """
        Format a mailbox name for IMAP commands.

        - Leaves INBOX as-is (special name).
        - If already quoted, return as-is.
        - Otherwise, wrap in double quotes so names with spaces or
          special characters (e.g. "[Gmail]/All Mail") parse correctly.
        """
        if mailbox.upper() == "INBOX":
            return "INBOX"
        if mailbox.startswith('"') and mailbox.endswith('"'):
            return mailbox
        return f'"{mailbox}"'

    def _ensure_selected(self, conn: imaplib.IMAP4, mailbox: str, readonly: bool) -> None:
        """
        Cache the selected mailbox to avoid repeated SELECT/EXAMINE.
        - readonly=True -> EXAMINE
        - readonly=False -> SELECT (read-write)
        """
        # Must be called with self._lock held.

        if self._selected_mailbox == mailbox:
            if readonly or self._selected_readonly is False:
                return
        imap_mailbox = self._format_mailbox_arg(mailbox)

        typ, _ = conn.select(imap_mailbox, readonly=readonly)
        if typ != "OK":
            raise IMAPError(f"select({mailbox!r}, readonly={readonly}) failed")
        self._selected_mailbox = mailbox
        self._selected_readonly = readonly

    def _assert_same_mailbox(self, refs: Sequence["EmailRef"], op_name: str) -> str:
        """
        Ensure all EmailRefs share the same mailbox.
        Returns the common mailbox name, or raises IMAPError.
        """
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
    
    def _parse_list_flags(self, raw: bytes) -> Set[str]:
        """
        Parse the flags portion of an IMAP LIST response line.

        Example raw:
            b'(\\HasChildren \\Noselect) "/" "[Gmail]"'

        Returns a set of upper-cased flag tokens, e.g.:
            {"\\HASCHILDREN", "\\NOSELECT"}
        """
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

        # Split on whitespace; normalize to upper-case
        return {f.upper() for f in flags_str.split() if f.strip()}
    
    def _run_with_conn(self, op):
        """
        Run an operation with a connection, handling:
        - thread-safety (RLock)
        - reconnect-on-abort (retry max_retries times)

        `op` is a callable taking a single `imaplib.IMAP4` argument.
        """
        last_exc: Optional[BaseException] = None
        attempts = self.max_retries + 1

        for attempt in range(attempts):
            with self._lock:
                conn = self._get_conn()
                try:
                    return op(conn)
                except imaplib.IMAP4.abort as e:
                    # Connection died; reset and retry with a fresh one.
                    last_exc = e
                    self._reset_conn()
                except imaplib.IMAP4.error as e:
                    # Non-abort protocol error; don't retry
                    raise IMAPError(f"IMAP operation failed: {e}") from e
            if attempt < attempts - 1 and self.backoff_seconds > 0:
                time.sleep(self.backoff_seconds)

        raise IMAPError(f"IMAP connection repeatedly aborted: {last_exc}") from last_exc

    def refresh_search_cache(self, *, mailbox: str, query: IMAPQuery) -> List[int]:
        """
        Refresh the cached UID list for (mailbox, query).
        """
        criteria = query.build() or "ALL"
        cache_key = (mailbox, criteria)

        def _impl(conn: imaplib.IMAP4) -> List[int]:
            self._ensure_selected(conn, mailbox, readonly=True)

            typ, data = conn.uid("SEARCH", None, criteria)
            if typ != "OK":
                raise IMAPError(f"SEARCH failed: {data}")

            raw = data[0] or b""
            # SEARCH returns ascending UIDs (oldest -> newest)
            uids_bytes = raw.split()
            uids = [int(x) for x in uids_bytes]

            # Store in cache while holding the lock (run_with_conn already does)
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
        """
        Cached, cursor-based paging over search results, newest-first.
        """

        if before_uid is not None and after_uid is not None:
            raise ValueError("Cannot specify both before_uid and after_uid")
    
        criteria = query.build() or "ALL"
        cache_key = (mailbox, criteria)

        with self._lock:
            uids = None if refresh else self._search_cache.get(cache_key)

        if uids is None:
            uids = self.refresh_search_cache(mailbox=mailbox, query=query)

        if not uids:
            return PagedSearchResult(refs=[], total=0, has_more=False)

        uids_sorted = uids
        if before_uid is not None:
            filtered = [uid for uid in uids_sorted if uid < before_uid]
            direction = "older"
        elif after_uid is not None:
            filtered = [uid for uid in uids_sorted if uid > after_uid]
            direction = "newer"
        else:
            filtered = uids_sorted
            direction = "initial"

        if not filtered:
            return PagedSearchResult(refs=[], total=len(uids), has_more=False)

        filtered_rev = list(reversed(filtered))
        page_uids = filtered_rev[:page_size]

        if not page_uids:
            return PagedSearchResult(refs=[], total=len(uids), has_more=False)

        refs = [EmailRef(uid=uid, mailbox=mailbox) for uid in page_uids]

        newest_uid = page_uids[0]
        oldest_uid = page_uids[-1]

        total_matches = len(uids)
        total_in_range = len(filtered)

        has_more = total_in_range > page_size
        next_before_uid = oldest_uid if has_more else None

        prev_after_uid: Optional[int] = None
        if direction in ("older", "initial"):
            if newest_uid < uids_sorted[-1]:
                prev_after_uid = newest_uid

        elif direction == "newer":
            if newest_uid < uids_sorted[-1]:
                prev_after_uid = newest_uid

        return PagedSearchResult(
            refs=refs,
            next_before_uid=next_before_uid,
            prev_after_uid=prev_after_uid,
            newest_uid=newest_uid,
            oldest_uid=oldest_uid,
            total=total_matches,
            has_more=has_more,
        )

    def search(self, *, mailbox: str, query: IMAPQuery, limit: int = 50) -> List["EmailRef"]:
        page = self.search_page_cached(
            mailbox=mailbox,
            query=query,
            page_size=limit,
            before_uid=None,
            after_uid=None,
            refresh=True,  # force a fresh SEARCH, also populates cache
        )
        return page.refs
    
    def fetch(self, refs: Sequence["EmailRef"], *, include_attachments: bool = False) -> List[EmailMessage]:
        if not refs:
            return []

        mailbox = self._assert_same_mailbox(refs, "fetch")

        required_uids = {r.uid for r in refs}

        def _impl(conn: imaplib.IMAP4) -> List[EmailMessage]:
            self._ensure_selected(conn, mailbox, readonly=True)

            uid_str = ",".join(str(r.uid) for r in refs)
            typ, data = conn.uid("FETCH", uid_str, "(UID RFC822 INTERNALDATE)")
            if typ != "OK":
                raise IMAPError(f"FETCH failed: {data}")
            if not data:
                return []
            
            partial: Dict[int, Dict[str, object]] = {}
            current_uid: Optional[int] = None

            i = 0
            n = len(data)
            while i < n:
                item = data[i]

                # Closing markers like b')' – usually end of a message block
                if isinstance(item, (bytes, bytearray)):
                    if item.strip() == b')':
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

                # Get payload; may be in item[1], or (on some servers) as next list element
                raw = item[1] if len(item) > 1 and isinstance(item[1], (bytes, bytearray)) else None
                used_next = False
                if raw is None and i + 1 < n and isinstance(data[i + 1], (bytes, bytearray)):
                    raw = data[i + 1]
                    used_next = True

                # New UID?
                m_uid = UID_RE.search(meta_str)
                if m_uid:
                    uid = int(m_uid.group(1))
                    # Only track UIDs we actually asked for
                    current_uid = uid if uid in required_uids else None

                if current_uid is None:
                    # Nothing to associate this chunk with
                    i += 2 if used_next else 1
                    continue

                bucket = partial.setdefault(
                    current_uid,
                    {"raw": b"", "internaldate": None},
                )

                # INTERNALDATE (might appear on first tuple only)
                m_internal = INTERNALDATE_RE.search(meta_str)
                if m_internal:
                    bucket["internaldate"] = m_internal.group(1)

                # RFC822 payload (can be chunked; append)
                if "RFC822" in meta_str.upper() and isinstance(raw, (bytes, bytearray)):
                    prev = bucket.get("raw") or b""
                    bucket["raw"] = prev + raw

                i += 2 if used_next else 1


            out: List[EmailMessage] = []
            for r in refs:
                info = partial.get(r.uid)
                if not info:
                    continue

                raw_bytes = info.get("raw") or b""
                internaldate_raw = info.get("internaldate")

                msg = parse_rfc822(
                    r,
                    raw_bytes,
                    include_attachments=include_attachments,
                    internaldate_raw=internaldate_raw,
                )
                out.append(msg)

            return out

        return self._run_with_conn(_impl)

    def fetch_overview(
        self,
        refs: Sequence["EmailRef"],
        *,
        preview_bytes: int = 1024,
    ) -> List[EmailOverview]:
        """
        Lightweight fetch: only FLAGS, selected headers (From, To, Subject, Date, Message-ID),
        and a small text preview from the body.
        """
        if not refs:
            return []
        mailbox = self._assert_same_mailbox(refs, "fetch_overview")

        def _impl(conn: imaplib.IMAP4) -> List[EmailOverview]:
            self._ensure_selected(conn, mailbox, readonly=True)

            uid_str = ",".join(str(r.uid) for r in refs)
            # FLAGS + headers + partial text body
            attrs = (
                f"(UID FLAGS INTERNALDATE "
                "BODY.PEEK[HEADER.FIELDS (From To Subject Date Message-ID Content-Type Content-Transfer-Encoding)] "
                f"BODY.PEEK[TEXT]<0.{preview_bytes}>)"
            )
            typ, data = conn.uid("FETCH", uid_str, attrs)
            if typ != "OK":
                raise IMAPError(f"FETCH overview failed: {data}")
            if not data:
                return []
            # Collect partial data per UID
            partial: Dict[int, Dict[str, object]] = {}
            current_uid: Optional[int] = None
            i = 0
            n = len(data)
            while i < n:
                item = data[i]

                # Closing marker like b')' – end of current message
                if isinstance(item, (bytes, bytearray)):
                    # defensive: reset current_uid on “)” or similar terminators
                    if item.strip() == b')':
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

                payload = item[1] if len(item) > 1 and isinstance(item[1], (bytes, bytearray)) else None

                m_uid = UID_RE.search(meta)
                if m_uid:
                    current_uid = int(m_uid.group(1))

                if current_uid is None:
                    i += 1
                    continue

                bucket = partial.setdefault(
                    current_uid,
                    {
                        "flags": set(),
                        "headers": None,
                        "preview": b"",
                        "internaldate": None,
                    },
                )

                # FLAGS (only present on the first tuple for the message)
                m_flags = FLAGS_RE.search(meta)
                if m_flags:
                    flags_str = m_flags.group(1).strip()
                    if flags_str:
                        bucket["flags"] = {f for f in flags_str.split() if f}

                # INTERNALDATE
                m_internal = INTERNALDATE_RE.search(meta)
                if m_internal:
                    bucket["internaldate"] = m_internal.group(1)

                # Headers (might be in a tuple with no UID, as in your sample)
                if HEADER_TOKEN_RE.search(meta) and isinstance(payload, (bytes, bytearray)):
                    bucket["headers"] = payload

                # Preview (BODY[TEXT] or BODY.PEEK[TEXT] etc.)
                if TEXT_TOKEN_RE.search(meta) and isinstance(payload, (bytes, bytearray)):
                    prev = bucket.get("preview") or b""
                    bucket["preview"] = prev + payload

                i += 1

            # Build EmailOverview objects in the same order as refs
            overviews: List[EmailOverview] = []
            for r in refs:
                info = partial.get(r.uid)
                if not info:
                    continue

                flags = set(info["flags"]) if isinstance(info["flags"], set) else set()
                header_bytes = info["headers"]
                preview_bytes_val = info["preview"] or b""
                internaldate_raw = info.get("internaldate")

                overviews.append(
                    parse_overview(
                        r,
                        flags,
                        header_bytes,
                        preview_bytes_val,
                        internaldate_raw=internaldate_raw,
                    )
                )

            return overviews

        return self._run_with_conn(_impl)
    
    def append(
        self,
        mailbox: str,
        msg: PyEmailMessage,
        *,
        flags: Optional[Set[str]] = None,
    ) -> EmailRef:
        """
        Append a message to `mailbox` and return an EmailRef.
        """
        def _impl(conn: imaplib.IMAP4) -> EmailRef:
            self._ensure_selected(conn, mailbox, readonly=False)

            flags_arg = None
            if flags:
                flags_arg = "(" + " ".join(sorted(flags)) + ")"

            date_time = imaplib.Time2Internaldate(time.time())
            raw_bytes = msg.as_bytes()
            imap_mailbox = self._format_mailbox_arg(mailbox)
            typ, data = conn.append(imap_mailbox, flags_arg, date_time, raw_bytes)
            if typ != "OK":
                raise IMAPError(f"APPEND to {mailbox!r} failed: {data}")

            uid: Optional[int] = None
            if data and data[0]:
                if isinstance(data[0], bytes):
                    resp = data[0].decode(errors="ignore")
                else:
                    resp = str(data[0])
                m = re.search(r"APPENDUID\s+\d+\s+(\d+)", resp)
                if m:
                    uid = int(m.group(1))

            if uid is None:
                typ_search, data_search = conn.uid("SEARCH", None, "ALL")
                if typ_search == "OK" and data_search and data_search[0]:
                    all_uids = [
                        int(x)
                        for x in data_search[0].split()
                        if x.strip()
                    ]
                    if all_uids:
                        uid = max(all_uids)

            if uid is None:
                raise IMAPError("APPEND succeeded but could not determine UID")

            return EmailRef(uid=uid, mailbox=mailbox)

        return self._run_with_conn(_impl)

    def add_flags(self, refs: Sequence["EmailRef"], *, flags: Set[str]) -> None:
        self._store(refs, mode="+FLAGS", flags=flags)

    def remove_flags(self, refs: Sequence["EmailRef"], *, flags: Set[str]) -> None:
        self._store(refs, mode="-FLAGS", flags=flags)

    def _store(self, refs: Sequence["EmailRef"], *, mode: str, flags: Set[str]) -> None:
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

    def expunge(self, mailbox: str = "INBOX") -> None:
        """
        Permanently remove messages flagged as \\Deleted in the given mailbox.
        """
        def _impl(conn: imaplib.IMAP4) -> None:
            self._ensure_selected(conn, mailbox, readonly=False)

            typ, data = conn.expunge()
            if typ != "OK":
                raise IMAPError(f"EXPUNGE failed: {data}")

        self._run_with_conn(_impl)

    def list_mailboxes(self) -> List[str]:
        """
        Return a list of *selectable* mailbox names (skip \\Noselect).
        """
        def _impl(conn: imaplib.IMAP4) -> List[str]:
            typ, data = conn.list()
            if typ != "OK":
                raise IMAPError(f"LIST failed: {data}")

            mailboxes: List[str] = []
            if not data:
                return mailboxes

            for raw in data:
                if not raw:
                    continue

                # Skip non-selectable mailboxes advertised with \Noselect
                flags = self._parse_list_flags(raw)
                if r"\NOSELECT" in flags:
                    continue

                name = parse_list_mailbox_name(raw)
                if name is not None:
                    mailboxes.append(name)

            return mailboxes

        return self._run_with_conn(_impl)

    def mailbox_status(self, mailbox: str = "INBOX") -> Dict[str, int]:
        """
        Return basic status counters for a mailbox, e.g.:
            {"messages": 1234, "unseen": 12}
        """
        def _impl(conn: imaplib.IMAP4) -> Dict[str, int]:
            imap_mailbox = self._format_mailbox_arg(mailbox)
            typ, data = conn.status(imap_mailbox, "(MESSAGES UNSEEN)")
            if typ != "OK":
                raise IMAPError(f"STATUS {mailbox!r} failed: {data}")

            if not data or not data[0]:
                raise IMAPError(f"STATUS {mailbox!r} returned empty data")

            # Example: b'INBOX (MESSAGES 42 UNSEEN 3)'
            if isinstance(data[0], bytes):
                s = data[0].decode(errors="ignore")
            else:
                s = str(data[0])

            # Extract the parenthesized part
            start = s.find("(")
            end = s.rfind(")")
            if start == -1 or end == -1 or end <= start:
                raise IMAPError(f"Unexpected STATUS response: {s!r}")

            payload = s[start + 1 : end]
            tokens = payload.split()
            status: Dict[str, int] = {}

            # tokens like ["MESSAGES", "42", "UNSEEN", "3"]
            for i in range(0, len(tokens) - 1, 2):
                key = tokens[i].upper()
                val_str = tokens[i + 1]
                try:
                    val = int(val_str)
                except ValueError:
                    continue

                if key == "MESSAGES":
                    status["messages"] = val
                elif key == "UNSEEN":
                    status["unseen"] = val
                else:
                    status[key.lower()] = val

            return status

        return self._run_with_conn(_impl)

    def move(
        self,
        refs: Sequence["EmailRef"],
        *,
        src_mailbox: str,
        dst_mailbox: str,
    ) -> None:
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

    def copy(
        self,
        refs: Sequence["EmailRef"],
        *,
        src_mailbox: str,
        dst_mailbox: str,
    ) -> None:
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

    def create_mailbox(self, name: str) -> None:
        def _impl(conn: imaplib.IMAP4) -> None:
            imap_name = self._format_mailbox_arg(name)
            typ, data = conn.create(imap_name)
            if typ != "OK":
                raise IMAPError(f"CREATE {name!r} failed: {data}")

        self._run_with_conn(_impl)

    def delete_mailbox(self, name: str) -> None:
        def _impl(conn: imaplib.IMAP4) -> None:
            imap_name = self._format_mailbox_arg(name)
            typ, data = conn.delete(imap_name)
            if typ != "OK":
                raise IMAPError(f"DELETE {name!r} failed: {data}")

        self._run_with_conn(_impl)

    def ping(self) -> None:
        """
        Minimal IMAP health check.
        """
        def _impl(conn: imaplib.IMAP4) -> None:
            typ, data = conn.noop()
            if typ != "OK":
                raise IMAPError(f"NOOP failed: {data}")

        self._run_with_conn(_impl)

    def close(self) -> None:
        with self._lock:
            self._reset_conn()

    def __enter__(self) -> "IMAPClient":
        # lazy connect;
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
