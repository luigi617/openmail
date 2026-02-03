from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from openmail.types import EmailRef, SendResult


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
        kinds = "; ".join({m.kind for m in self.methods})
        return (
            f"UnsubscribeCandidate("
            f"from={self.from_email!r}, "
            f"methods={kinds})"
        )


@dataclass(frozen=True)
class UnsubscribeActionResult:
    ref: EmailRef
    method: Optional[UnsubscribeMethod]
    sent: bool
    send_result: Optional[SendResult] = None
    note: Optional[str] = None

    def __repr__(self) -> str:
        detail = self.send_result.detail if self.send_result else "None"
        return (
            "UnsubscribeActionResult("
            f"sent={self.sent!r}, "
            f"detail={detail!r})"
        )
