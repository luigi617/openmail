from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class AuthContext:
    """
    Extra context an auth method may need.
    (Keep this minimal; extend later.)
    """
    host: str
    port: int
    username: Optional[str] = None

@runtime_checkable
class SMTPAuth(Protocol):
    """
    Something that knows how to authenticate an smtplib.SMTP-like object.
    """
    def apply_smtp(self, server, ctx: AuthContext) -> None: ...

@runtime_checkable
class IMAPAuth(Protocol):
    """
    Something that knows how to authenticate an imaplib.IMAP4-like object.
    """
    def apply_imap(self, conn, ctx: AuthContext) -> None: ...