from __future__ import annotations
import imaplib
from dataclasses import dataclass
from typing import List, Optional, Sequence, Set

from email_management.auth import AuthContext

from email_management import IMAPConfig
from email_management.errors import AuthError, ConfigError, IMAPError
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
