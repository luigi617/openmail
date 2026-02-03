from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from openmail.auth import IMAPAuth, SMTPAuth


@dataclass(frozen=True)
class SMTPConfig:
    host: str
    port: int = 587
    use_starttls: bool = True
    use_ssl: bool = False
    timeout: float = 30.0
    from_email: Optional[str] = None
    auth: Optional[SMTPAuth] = None


@dataclass(frozen=True)
class IMAPConfig:
    host: str
    port: int = 993
    use_ssl: bool = True
    timeout: float = 30.0
    auth: Optional[IMAPAuth] = None
