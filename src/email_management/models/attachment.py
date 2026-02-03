from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


def _normalize_content_id(cid: Optional[str]) -> Optional[str]:
    if not cid:
        return None
    c = cid.strip()
    # handle "<...>"
    if c.startswith("<") and c.endswith(">") and len(c) >= 2:
        c = c[1:-1].strip()
    return c or None


def _normalize_disposition(d: Optional[str]) -> Optional[str]:
    if not d:
        return None
    d2 = d.strip().lower()
    if d2 in ("inline", "attachment"):
        return d2
    return d2 or None

@dataclass(frozen=True)
class AttachmentMeta:
    idx: int
    part: str
    filename: str
    content_type: str
    size: int
    content_id: Optional[str] = None
    disposition: Optional[str] = None
    is_inline: bool = False
    content_location: Optional[str] = None

    def __post_init__(self) -> None:
        # frozen=True, so use object.__setattr__
        object.__setattr__(self, "content_id", _normalize_content_id(self.content_id))
        object.__setattr__(self, "disposition", _normalize_disposition(self.disposition))

        # If caller forgot to set is_inline, infer a sensible default:
        # - explicit inline disposition OR
        # - has content_id and is an image (typical CID-inline case)
        inferred_inline = (
            (self.disposition == "inline")
            or (self.content_id is not None and self.content_type.lower().startswith("image/"))
        )
        # Only override if it looks unset / default
        if self.is_inline is False and inferred_inline:
            object.__setattr__(self, "is_inline", True)

    def __repr__(self) -> str:
        extra = []
        if self.disposition:
            extra.append(f"disposition={self.disposition!r}")
        if self.is_inline:
            extra.append("is_inline=True")
        if self.content_id:
            extra.append(f"content_id={self.content_id!r}")
        if self.content_location:
            extra.append(f"content_location={self.content_location!r}")

        extra_s = (", " + ", ".join(extra)) if extra else ""
        return (
            f"AttachmentMeta("
            f"idx={self.idx!r}, "
            f"part={self.part!r}, "
            f"filename={self.filename!r}, "
            f"content_type={self.content_type!r}, "
            f"size={self.size} bytes"
            f"{extra_s})"
        )

    def to_dict(self) -> dict:
        # Preserve existing keys + add new ones.
        return {
            "idx": self.idx,
            "part": self.part,
            "filename": self.filename,
            "content_type": self.content_type,
            "size": self.size,
            "content_id": self.content_id,
            "disposition": self.disposition,
            "is_inline": self.is_inline,
            "content_location": self.content_location,
        }


@dataclass(frozen=True)
class Attachment(AttachmentMeta):
    data: bytes = b""

    def __repr__(self) -> str:
        # Keep Attachment repr aligned with AttachmentMeta, but still indicate it’s Attachment.
        extra = []
        if self.disposition:
            extra.append(f"disposition={self.disposition!r}")
        if self.is_inline:
            extra.append("is_inline=True")
        if self.content_id:
            extra.append(f"content_id={self.content_id!r}")
        if self.content_location:
            extra.append(f"content_location={self.content_location!r}")

        extra_s = (", " + ", ".join(extra)) if extra else ""
        return (
            f"Attachment("
            f"idx={self.idx!r}, "
            f"part={self.part!r}, "
            f"filename={self.filename!r}, "
            f"content_type={self.content_type!r}, "
            f"size={self.size} bytes"
            f"{extra_s})"
        )

    def to_dict(self) -> dict:
        return {
            "idx": self.idx,
            "part": self.part,
            "filename": self.filename,
            "content_type": self.content_type,
            "size": self.size,
            "content_id": self.content_id,
            "disposition": self.disposition,
            "is_inline": self.is_inline,
            "content_location": self.content_location,
        }