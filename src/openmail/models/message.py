from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Set

from openmail.types import EmailRef

if TYPE_CHECKING:
    from openmail.models.attachment import Attachment

@dataclass(frozen=True)
class EmailAddress:
    email: str
    name: Optional[str] = None

    @property
    def display(self) -> str:
        if self.name:
            return f"{self.name} <{self.email}>"
        return self.email

    def __str__(self) -> str:
        return self.display
    
    def __repr__(self) -> str:
        return f"EmailAddress(email={self.email!r}, name={self.name!r})"
    
    def to_dict(self) -> dict:
        return {
            "email": self.email,
            "name": self.name,
        }
    
@dataclass(frozen=True)
class EmailMessage:
    ref: EmailRef
    subject: str
    from_email: EmailAddress
    to: Sequence[EmailAddress]
    cc: Sequence[EmailAddress] = field(default_factory=list)
    bcc: Sequence[EmailAddress] = field(default_factory=list)
    text: Optional[str] = None
    html: Optional[str] = None
    attachments: List[Attachment] = field(default_factory=list)

    # IMAP metadata
    received_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    message_id: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"EmailMessage("
            f"subject={self.subject!r}, "
            f"from={self.from_email!r}, "
            f"to={list(self.to)!r}, "
            f"received_at={self.received_at!r})"
            f"attachments={len(self.attachments)})"
        )
    
    def to_dict(self) -> dict:
        return {
            "ref": self.ref.to_dict(),
            "subject": self.subject,
            "from_email": self.from_email.to_dict(),
            "to": [addr.to_dict() for addr in self.to],
            "cc": [addr.to_dict() for addr in self.cc],
            "bcc": [addr.to_dict() for addr in self.bcc],
            "text": self.text,
            "html": self.html,
            "attachments": [att.to_dict() for att in self.attachments],
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "message_id": self.message_id,
            "headers": self.headers,
        }
    
@dataclass(frozen=True)
class EmailOverview:
    ref: EmailRef
    subject: str
    from_email: EmailAddress
    to: Sequence[EmailAddress]
    flags: Set[str]
    headers: Dict[str, str]
    received_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None

    def __repr__(self) -> str:
        return (
            f"EmailOverview("
            f"subject={self.subject!r}, "
            f"from={self.from_email!r}, "
            f"to={list(self.to)!r}, "
            f"received_at={self.received_at!r})"
        )
    def to_dict(self) -> dict:
        return {
            "ref": self.ref.to_dict(),
            "subject": self.subject,
            "from_email": self.from_email.to_dict(),
            "to": [addr.to_dict() for addr in self.to],
            "flags": list(self.flags),
            "headers": self.headers,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
        }
