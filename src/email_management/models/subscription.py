from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

from email_management.types import EmailRef, SendResult


@dataclass(frozen=True)
class UnsubscribeMethod:
    """
    One unsubscribe mechanism from List-Unsubscribe.
    """
    kind: str  # "mailto" | "http"
    value: str


@dataclass(frozen=True)
class UnsubscribeCandidate:
    """
    An email that supports unsubscribe.
    """
    ref: EmailRef
    from_email: str
    subject: str
    methods: List[UnsubscribeMethod]

    def __repr__(self) -> str:
        return (
            f"UnsubscribeCandidate("
            f"from={self.from_email!r}, "
            f"methods={"; ".join(set([m.kind for m in self.methods]))})"
        )


@dataclass(frozen=True)
class UnsubscribeActionResult:
    ref: EmailRef
    method: Optional[UnsubscribeMethod]
    sent: bool
    send_result: Optional[SendResult] = None
    note: Optional[str] = None

    def __repr__(self) -> str:
        return (
            f"UnsubscribeActionResult("
            f"sent={self.sent!r}, "
            f"detail={self.send_result.detail if self.send_result else "None"})"
        )
