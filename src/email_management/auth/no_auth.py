from __future__ import annotations
from dataclasses import dataclass
from email_management.auth.base import AuthContext

@dataclass(frozen=True)
class NoAuth:
    """
    Represents 'no authentication required'. Useful for SMTP relays
    or IMAP/SMTP servers that don't require login for this client.
    """
    def apply_smtp(self, server, ctx: AuthContext) -> None:
        return

    def apply_imap(self, conn, ctx: AuthContext) -> None:
        return