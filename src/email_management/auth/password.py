from __future__ import annotations
from dataclasses import dataclass
from email_management.auth.base import AuthContext
from email_management.errors import AuthError

@dataclass(frozen=True)
class PasswordAuth:
    username: str
    password: str

    def apply_smtp(self, server, ctx: AuthContext) -> None:
        try:
            server.login(self.username, self.password)
        except Exception as e:
            raise AuthError(f"SMTP login failed: {e}") from e

    def apply_imap(self, conn, ctx: AuthContext) -> None:
        try:
            typ, _ = conn.login(self.username, self.password)
            if typ != "OK":
                raise AuthError("IMAP login failed (non-OK response)")
        except Exception as e:
            raise AuthError(f"IMAP login failed: {e}") from e
