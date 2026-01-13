from __future__ import annotations
import imaplib
import time
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Set, Dict
from email.message import EmailMessage as PyEmailMessage 

from email_management.auth import AuthContext
from email_management import IMAPConfig
from email_management.errors import ConfigError, IMAPError
from email_management.models import EmailMessage
from email_management.types import EmailRef

from email_management.imap.query import IMAPQuery
from email_management.imap.parser import parse_rfc822

@dataclass(frozen=True)
class IMAPClient:
    config: IMAPConfig

    @classmethod
    def from_config(cls, config: IMAPConfig) -> "IMAPClient":
        if not config.host:
            raise ConfigError("IMAP host required")
        if not config.port:
            raise ConfigError("IMAP port required")
        return cls(config)

    def _connect(self) -> imaplib.IMAP4:
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
            
    def search(self, *, mailbox: str, query: IMAPQuery, limit: int = 50) -> List["EmailRef"]:
        conn = None
        try:
            conn = self._connect()
            if conn.select(mailbox)[0] != "OK":
                raise IMAPError(f"select({mailbox}) failed")

            typ, data = conn.uid("SEARCH", None, query.build())
            if typ != "OK":
                raise IMAPError(f"SEARCH failed: {data}")

            uids = (data[0] or b"").split()
            uids = list(reversed(uids))[:limit]
            return [EmailRef(uid=int(x), mailbox=mailbox) for x in uids]
        finally:
            if conn is not None:
                try: conn.logout()
                except Exception: pass

    def fetch(self, refs: Sequence["EmailRef"], *, include_attachments: bool = False) -> List[EmailMessage]:
        if not refs:
            return []
        mailbox = refs[0].mailbox
        conn = None
        try:
            conn = self._connect()
            if conn.select(mailbox)[0] != "OK":
                raise IMAPError(f"select({mailbox}) failed")

            out: List[EmailMessage] = []
            for r in refs:
                typ, data = conn.uid("FETCH", str(r.uid), "(RFC822)")
                if typ != "OK" or not data or not data[0]:
                    continue
                raw = data[0][1]
                out.append(parse_rfc822(r, raw, include_attachments=include_attachments))
            return out
        finally:
            if conn is not None:
                try: conn.logout()
                except Exception: pass

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
        conn = None
        try:
            conn = self._connect()

            # Select mailbox to ensure it exists and we get a current UID set
            if conn.select(mailbox)[0] != "OK":
                raise IMAPError(f"select({mailbox}) failed for APPEND")

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

        except imaplib.IMAP4.error as e:
            raise IMAPError(f"IMAP APPEND failed: {e}") from e
        finally:
            if conn is not None:
                try:
                    conn.logout()
                except Exception:
                    pass

    def add_flags(self, refs: Sequence["EmailRef"], *, flags: Set[str]) -> None:
        self._store(refs, mode="+FLAGS", flags=flags)

    def remove_flags(self, refs: Sequence["EmailRef"], *, flags: Set[str]) -> None:
        self._store(refs, mode="-FLAGS", flags=flags)

    def _store(self, refs: Sequence["EmailRef"], *, mode: str, flags: Set[str]) -> None:
        if not refs:
            return
        mailbox = refs[0].mailbox
        conn = None
        try:
            conn = self._connect()
            if conn.select(mailbox)[0] != "OK":
                raise IMAPError(f"select({mailbox}) failed")
            uids = ",".join(str(r.uid) for r in refs)
            flag_list = "(" + " ".join(sorted(flags)) + ")"
            typ, data = conn.uid("STORE", uids, mode, flag_list)
            if typ != "OK":
                raise IMAPError(f"STORE failed: {data}")
        finally:
            if conn is not None:
                try: conn.logout()
                except Exception: pass

    def expunge(self, mailbox: str = "INBOX") -> None:
        """
        Permanently remove messages flagged as \\Deleted in the given mailbox.
        """
        conn = None
        try:
            conn = self._connect()
            if conn.select(mailbox)[0] != "OK":
                raise IMAPError(f"select({mailbox}) failed for EXPUNGE")

            typ, data = conn.expunge()
            if typ != "OK":
                raise IMAPError(f"EXPUNGE failed: {data}")

        except imaplib.IMAP4.error as e:
            raise IMAPError(f"IMAP EXPUNGE failed: {e}") from e
        finally:
            if conn is not None:
                try:
                    conn.logout()
                except Exception:
                    pass

    def list_mailboxes(self) -> List[str]:
        """
        Return a list of mailbox (folder) names.
        """
        conn = None
        try:
            conn = self._connect()
            typ, data = conn.list()
            if typ != "OK":
                raise IMAPError(f"LIST failed: {data}")

            mailboxes: List[str] = []
            if not data:
                return mailboxes

            for raw in data:
                if not raw:
                    continue
                # raw is usually bytes like: b'(\\HasNoChildren) "/" "INBOX"'
                if isinstance(raw, bytes):
                    s = raw.decode(errors="ignore")
                else:
                    s = str(raw)

                # Split into: FLAGS, DELIM, NAME
                parts = s.split(" ", 2)
                if len(parts) < 3:
                    continue
                name = parts[2].strip()
                # Strip surrounding quotes if present
                if name.startswith('"') and name.endswith('"'):
                    name = name[1:-1]
                mailboxes.append(name)

            return mailboxes

        except imaplib.IMAP4.error as e:
            raise IMAPError(f"IMAP LIST failed: {e}") from e
        finally:
            if conn is not None:
                try:
                    conn.logout()
                except Exception:
                    pass

    def mailbox_status(self, mailbox: str = "INBOX") -> Dict[str, int]:
        """
        Return basic status counters for a mailbox, e.g.:
            {"messages": 1234, "unseen": 12}
        """
        conn = None
        try:
            conn = self._connect()
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

        except imaplib.IMAP4.error as e:
            raise IMAPError(f"IMAP STATUS failed: {e}") from e
        finally:
            if conn is not None:
                try:
                    conn.logout()
                except Exception:
                    pass

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

        conn = None
        try:
            conn = self._connect()
            if conn.select(src_mailbox)[0] != "OK":
                raise IMAPError(f"select({src_mailbox}) failed")

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

            conn.expunge()

        except imaplib.IMAP4.error as e:
            raise IMAPError(f"IMAP MOVE failed: {e}") from e
        finally:
            if conn is not None:
                try:
                    conn.logout()
                except Exception:
                    pass

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

        conn = None
        try:
            conn = self._connect()
            if conn.select(src_mailbox)[0] != "OK":
                raise IMAPError(f"select({src_mailbox}) failed")

            uids = ",".join(str(r.uid) for r in refs)
            typ, data = conn.uid("COPY", uids, dst_mailbox)
            if typ != "OK":
                raise IMAPError(f"COPY failed: {data}")

        except imaplib.IMAP4.error as e:
            raise IMAPError(f"IMAP COPY failed: {e}") from e
        finally:
            if conn is not None:
                try:
                    conn.logout()
                except Exception:
                    pass

    def create_mailbox(self, name: str) -> None:
        
        conn = None
        try:
            conn = self._connect()
            typ, data = conn.create(name)
            if typ != "OK":
                raise IMAPError(f"CREATE {name!r} failed: {data}")
        except imaplib.IMAP4.error as e:
            raise IMAPError(f"IMAP CREATE failed: {e}") from e
        finally:
            if conn is not None:
                try:
                    conn.logout()
                except Exception:
                    pass

    def delete_mailbox(self, name: str) -> None:
        conn = None
        try:
            conn = self._connect()
            typ, data = conn.delete(name)
            if typ != "OK":
                raise IMAPError(f"DELETE {name!r} failed: {data}")
        except imaplib.IMAP4.error as e:
            raise IMAPError(f"IMAP DELETE failed: {e}") from e
        finally:
            if conn is not None:
                try:
                    conn.logout()
                except Exception:
                    pass

    def ping(self) -> None:
        """
        Minimal IMAP health check.
        Raises IMAPError if NOOP fails.
        """
        conn = None
        try:
            conn = self._connect()
            typ, data = conn.noop()
            if typ != "OK":
                raise IMAPError(f"NOOP failed: {data}")
        except imaplib.IMAP4.error as e:
            raise IMAPError(f"IMAP ping failed: {e}") from e
        finally:
            if conn is not None:
                try:
                    conn.logout()
                except Exception:
                    pass
