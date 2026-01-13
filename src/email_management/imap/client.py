from __future__ import annotations
from email.parser import BytesParser
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
from email_management.imap.parser import parse_rfc822



@dataclass
class IMAPClient:
    config: IMAPConfig
    _conn: imaplib.IMAP4 | None = field(default=None, init=False, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _selected_mailbox: str | None = field(default=None, init=False, repr=False)
    _selected_readonly: bool | None = field(default=None, init=False, repr=False)

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

    def _ensure_selected(self, conn: imaplib.IMAP4, mailbox: str, readonly: bool) -> None:
        """
        Cache the selected mailbox to avoid repeated SELECT/EXAMINE.
        - readonly=True -> EXAMINE
        - readonly=False -> SELECT (read-write)
        Reuses a read-write selection for readonly operations, but not vice versa.
        Must be called with self._lock held.
        """
        if self._selected_mailbox == mailbox:
            if readonly or self._selected_readonly is False:
                return

        typ, _ = conn.select(mailbox, readonly=readonly)
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
                    # loop will retry
                except imaplib.IMAP4.error as e:
                    # Non-abort protocol error; don't retry
                    raise IMAPError(f"IMAP operation failed: {e}") from e
            if attempt < attempts - 1 and self.backoff_seconds > 0:
                time.sleep(self.backoff_seconds)

        # If we get here, all attempts failed due to abort
        raise IMAPError(f"IMAP connection repeatedly aborted: {last_exc}") from last_exc

    def search(self, *, mailbox: str, query: IMAPQuery, limit: int = 50) -> List["EmailRef"]:
        def _impl(conn: imaplib.IMAP4) -> List["EmailRef"]:
            self._ensure_selected(conn, mailbox, readonly=True)

            typ, data = conn.uid("SEARCH", None, query.build())
            if typ != "OK":
                raise IMAPError(f"SEARCH failed: {data}")

            uids = (data[0] or b"").split()
            uids = list(reversed(uids))[:limit]
            return [EmailRef(uid=int(x), mailbox=mailbox) for x in uids]

        return self._run_with_conn(_impl)

    def fetch(self, refs: Sequence["EmailRef"], *, include_attachments: bool = False) -> List[EmailMessage]:
        if not refs:
            return []

        mailbox = self._assert_same_mailbox(refs, "fetch")

        uid_to_ref: Dict[int, EmailRef] = {r.uid: r for r in refs}

        def _impl(conn: imaplib.IMAP4) -> List[EmailMessage]:
            self._ensure_selected(conn, mailbox, readonly=True)

            uid_str = ",".join(str(r.uid) for r in refs)
            typ, data = conn.uid("FETCH", uid_str, "(RFC822)")
            if typ != "OK":
                raise IMAPError(f"FETCH failed: {data}")
            
            out: List[EmailMessage] = []

            # data is a list of response tuples; we care about tuples (meta, raw_bytes)
            for item in data:
                if not item or not isinstance(item, tuple) or len(item) < 2:
                    continue
                meta, raw = item[0], item[1]
                if not isinstance(meta, (bytes, bytearray)):
                    continue
                meta_str = meta.decode(errors="ignore")

                m = re.search(r"UID\s+(\d+)", meta_str)
                if not m:
                    continue
                uid = int(m.group(1))
                ref = uid_to_ref.get(uid)
                if ref is None:
                    continue

                out.append(parse_rfc822(ref, raw, include_attachments=include_attachments))

            # Preserve original order of refs as much as possible
            out_by_uid = {msg.ref.uid: msg for msg in out} if out and hasattr(out[0], "ref") else None
            if out_by_uid:
                ordered: List[EmailMessage] = []
                for r in refs:
                    msg = out_by_uid.get(r.uid)
                    if msg is not None:
                        ordered.append(msg)
                return ordered

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
                f"(FLAGS "
                "BODY.PEEK[HEADER.FIELDS (From To Subject Date Message-ID)] "
                f"BODY.PEEK[TEXT]<0.{preview_bytes}>)"
            )
            typ, data = conn.uid("FETCH", uid_str, attrs)
            if typ != "OK":
                raise IMAPError(f"FETCH overview failed: {data}")

            # Collect partial data per UID
            partial: Dict[int, Dict[str, object]] = {}

            for item in data:
                if not item or not isinstance(item, tuple) or len(item) < 2:
                    continue
                meta_raw, payload = item[0], item[1]
                if not isinstance(meta_raw, (bytes, bytearray)):
                    continue
                meta = meta_raw.decode(errors="ignore")

                m_uid = re.search(r"UID\s+(\d+)", meta)
                if not m_uid:
                    continue
                uid = int(m_uid.group(1))
                bucket = partial.setdefault(uid, {"flags": set(), "headers": None, "preview": b""})

                # FLAGS
                m_flags = re.search(r"FLAGS\s*\(([^)]*)\)", meta)
                if m_flags:
                    flags_str = m_flags.group(1).strip()
                    if flags_str:
                        flags = {f for f in flags_str.split() if f}
                        bucket["flags"] = flags

                # Headers
                if "BODY[HEADER.FIELDS" in meta:
                    bucket["headers"] = payload

                # Preview
                if "BODY[TEXT]<0." in meta:
                    # This may be one or more chunks; append
                    prev = bucket.get("preview") or b""
                    bucket["preview"] = prev + payload

            # Build EmailOverview objects in the same order as refs
            overviews: List[EmailOverview] = []
            for r in refs:
                info = partial.get(r.uid)
                if not info:
                    continue

                flags = set(info["flags"]) if isinstance(info["flags"], set) else set()
                header_bytes = info["headers"]
                preview_bytes_val = info["preview"] or b""

                subject = None
                from_email = None
                to_addrs: List[str] = []
                headers: Dict[str, str] = {}

                if isinstance(header_bytes, (bytes, bytearray)):
                    msg = BytesParser(policy=default_policy).parsebytes(header_bytes)
                    subject = msg.get("Subject")
                    from_email = msg.get("From")
                    to_raw = msg.get_all("To", [])
                    # msg.get_all returns list; join and split by comma is simplistic but ok
                    to_combined = ", ".join(to_raw)
                    if to_combined:
                        to_addrs = [addr.strip() for addr in to_combined.split(",") if addr.strip()]
                    # Optionally copy all headers into a dict
                    for k, v in msg.items():
                        headers[k] = str(v)

                preview_text = preview_bytes_val.decode("utf-8", errors="replace")

                overviews.append(
                    EmailOverview(
                        ref=r,
                        subject=subject,
                        from_email=from_email,
                        to=to_addrs,
                        flags=flags,
                        preview=preview_text,
                        headers=headers,
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
            # Select mailbox to ensure it exists and we get a current UID set
            self._ensure_selected(conn, mailbox, readonly=False)

            # Build flags string like "(\\Draft \\Seen)" or None
            flags_arg = None
            if flags:
                flags_arg = "(" + " ".join(sorted(flags)) + ")"

            # imaplib.Time2Internaldate for the current time
            date_time = imaplib.Time2Internaldate(time.time())
            raw_bytes = msg.as_bytes()

            typ, data = conn.append(mailbox, flags_arg, date_time, raw_bytes)
            if typ != "OK":
                raise IMAPError(f"APPEND to {mailbox!r} failed: {data}")

            # Try to parse UIDPLUS response: e.g. [b'[APPENDUID 38505 3955]']
            uid: Optional[int] = None
            if data and data[0]:
                if isinstance(data[0], bytes):
                    resp = data[0].decode(errors="ignore")
                else:
                    resp = str(data[0])
                m = re.search(r"APPENDUID\s+\d+\s+(\d+)", resp)
                if m:
                    uid = int(m.group(1))

            # Fallback: if UIDPLUS not available, search ALL and take max UID
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
                # APPEND succeeded but we cannot produce a stable EmailRef
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
        Return a list of mailbox (folder) names.
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
            typ, data = conn.status(mailbox, "(MESSAGES UNSEEN)")
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

            typ, data = conn.uid("MOVE", uids, dst_mailbox)
            if typ == "OK":
                return

            typ_copy, data_copy = conn.uid("COPY", uids, dst_mailbox)
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
            typ, data = conn.uid("COPY", uids, dst_mailbox)
            if typ != "OK":
                raise IMAPError(f"COPY failed: {data}")

        self._run_with_conn(_impl)

    def create_mailbox(self, name: str) -> None:
        def _impl(conn: imaplib.IMAP4) -> None:
            typ, data = conn.create(name)
            if typ != "OK":
                raise IMAPError(f"CREATE {name!r} failed: {data}")

        self._run_with_conn(_impl)

    def delete_mailbox(self, name: str) -> None:
        def _impl(conn: imaplib.IMAP4) -> None:
            typ, data = conn.delete(name)
            if typ != "OK":
                raise IMAPError(f"DELETE {name!r} failed: {data}")

        self._run_with_conn(_impl)

    def ping(self) -> None:
        """
        Minimal IMAP health check.
        Raises IMAPError if NOOP fails.
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
