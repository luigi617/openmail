from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AttachmentMeta:
    idx: int
    part: str
    filename: str
    content_type: str
    size: int

    def __repr__(self) -> str:
        return (
            f"AttachmentMeta("
            f"idx={self.idx!r}, "
            f"part={self.part!r}, "
            f"filename={self.filename!r}, "
            f"content_type={self.content_type!r}, "
            f"size={self.size} bytes)"
        )
    
    def to_dict(self) -> dict:
        return {
            "idx": self.idx,
            "part": self.part,
            "filename": self.filename,
            "content_type": self.content_type,
            "size": self.size,
        }
    
@dataclass(frozen=True)
class Attachment(AttachmentMeta):
    data: bytes
    
    def __repr__(self) -> str:
        return (
            f"Attachment("
            f"idx={self.idx!r}, "
            f"part={self.part!r}, "
            f"filename={self.filename!r}, "
            f"content_type={self.content_type!r}, "
            f"size={self.size} bytes)"
        )
    
    def to_dict(self) -> dict:
        return {
            "idx": self.idx,
            "part": self.part,
            "filename": self.filename,
            "content_type": self.content_type,
            "size": self.size,
        }