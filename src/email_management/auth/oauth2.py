from __future__ import annotations
import base64
from dataclasses import dataclass
from typing import Callable
from email_management.auth.base import AuthContext
from email_management.errors import AuthError

@dataclass(frozen=True)
class OAuth2Auth:
    """
    XOAUTH2-based auth. You provide a function that returns a fresh access token.
    - token_provider() -> access_token (string)
    """
    username: str
    token_provider: Callable[..., str]

    def _raw_xoauth2(self, access_token: str) -> str:
        return f"user={self.username}\x01auth=Bearer {access_token}\x01\x01"

    def apply_imap(self, conn, ctx: AuthContext) -> None:
        try:
            token = self.token_provider()
            if not token:
                raise AuthError("OAuth2 token provider returned empty token")

            auth_bytes = self._raw_xoauth2(token).encode("utf-8")

            def auth_cb(_):
                return auth_bytes

            typ, data = conn.authenticate("XOAUTH2", auth_cb)
            if typ != "OK":
                raise AuthError(f"IMAP XOAUTH2 auth failed (non-OK response: {typ}, {data})")
        except Exception as e:
            raise AuthError(f"IMAP XOAUTH2 auth failed: {e}") from e

    def apply_smtp(self, server, ctx: AuthContext) -> None:
        """
        smtplib doesn't expose a single 'authenticate XOAUTH2' helper,
        so we send AUTH XOAUTH2 with a base64-encoded initial response.
        """
        try:
            token = self.token_provider()
            if not token:
                raise AuthError("OAuth2 token provider returned empty token")

            raw = self._raw_xoauth2(token)
            auth_b64 = base64.b64encode(raw.encode("utf-8")).decode("ascii")

            code, resp = server.docmd("AUTH", "XOAUTH2 " + auth_b64)
            if code != 235:
                raise AuthError(f"SMTP XOAUTH2 auth failed: {code} {resp!r}")
        except Exception as e:
            raise AuthError(f"SMTP XOAUTH2 auth failed: {e}") from e