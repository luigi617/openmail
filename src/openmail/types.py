from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EmailRef:
    uid: int
    mailbox: str = "INBOX"

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "mailbox": self.mailbox,
        }

@dataclass(frozen=True)
class SendResult:
    ok: bool
    message_id: Optional[str] = None
    detail: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "message_id": self.message_id,
            "detail": self.detail,
        }
