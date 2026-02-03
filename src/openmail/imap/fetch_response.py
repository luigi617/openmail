# openmail/imap/fetch_response.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional, Sequence, Tuple
import re


UID_RE = re.compile(r"UID\s+(\d+)", re.IGNORECASE)
INTERNALDATE_RE = re.compile(r'INTERNALDATE\s+"([^"]+)"', re.IGNORECASE)
FLAGS_RE = re.compile(r"FLAGS\s*\(([^)]*)\)", re.IGNORECASE)

# Used for parsing FETCH section results
MIME_TOKEN_RE = re.compile(r"BODY\[(\d+(?:\.\d+)*)\.MIME\]", re.IGNORECASE)
BODY_TOKEN_RE = re.compile(r"BODY\[(\d+(?:\.\d+)*)\]", re.IGNORECASE)
HEADER_PEEK_RE = re.compile(r"BODY\[HEADER\]", re.IGNORECASE)


@dataclass(frozen=True)
class FetchPiece:
    """
    A normalized piece of a FETCH response.

    meta: decoded string metadata from the FETCH tuple element.
    payload: bytes payload (if present), else None.
    """
    meta: str
    payload: Optional[bytes]


def _extract_payload_from_fetch_item(
    item: tuple, data: Sequence[object], i: int
) -> Tuple[Optional[bytes], bool]:
    """
    Returns (payload_bytes, used_next_element).

    imaplib can return:
      - (meta, payload)
      - (meta, None) then payload as next bytes item
    """
    raw = item[1] if len(item) > 1 and isinstance(item[1], (bytes, bytearray)) else None
    used_next = False
    if raw is None and i + 1 < len(data) and isinstance(data[i + 1], (bytes, bytearray)):
        raw = data[i + 1]
        used_next = True
    return (bytes(raw) if isinstance(raw, (bytes, bytearray)) else None), used_next


def iter_fetch_pieces(data: Sequence[object]) -> Iterator[FetchPiece]:
    """
    Normalize imaplib FETCH response data into (meta_str, payload_bytes?) pieces.

    Skips non-tuple elements except tuple metadata; ignores the b")" terminators.
    """
    i = 0
    n = len(data)
    while i < n:
        item = data[i]

        # b")" terminator or other raw bytes => skip
        if isinstance(item, (bytes, bytearray)):
            i += 1
            continue

        if not isinstance(item, tuple) or not item:
            i += 1
            continue

        meta_raw = item[0]
        if not isinstance(meta_raw, (bytes, bytearray)):
            i += 1
            continue

        meta_str = meta_raw.decode(errors="ignore")
        payload, used_next = _extract_payload_from_fetch_item(item, data, i)
        yield FetchPiece(meta=meta_str, payload=payload)

        i += 2 if used_next else 1


def parse_uid(meta: str) -> Optional[int]:
    m = UID_RE.search(meta)
    return int(m.group(1)) if m else None


def parse_internaldate(meta: str) -> Optional[str]:
    m = INTERNALDATE_RE.search(meta)
    return m.group(1) if m else None


def parse_flags(meta: str) -> set[str]:
    m = FLAGS_RE.search(meta)
    if not m:
        return set()
    flags_str = m.group(1).strip()
    return {f for f in flags_str.split() if f} if flags_str else set()


def has_header_peek(meta: str) -> bool:
    return bool(HEADER_PEEK_RE.search(meta))


def match_section_mime(meta: str) -> Optional[str]:
    m = MIME_TOKEN_RE.search(meta)
    return m.group(1) if m else None


def match_section_body(meta: str) -> Optional[str]:
    """
    Returns section id for BODY[...] but NOT BODY[...MIME].
    """
    if MIME_TOKEN_RE.search(meta):
        return None
    m = BODY_TOKEN_RE.search(meta)
    return m.group(1) if m else None
