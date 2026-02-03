# email_management/imap/inline_images.py
from __future__ import annotations

import base64
import re
from typing import Dict, Iterable, Optional
from urllib.parse import unquote

from email_management.models import AttachmentMeta

_IMG_SRC_RE = re.compile(r'(<img\b[^>]*\bsrc=["\'])([^"\']+)(["\'])', re.IGNORECASE)

def _cid_variants(cid_src: str) -> list[str]:
    """
    Turn 'cid:image001.png@01DC....' into candidates:
      - image001.png@01DC...
      - image001.png
    Also handles <...> and urlencoding.
    """
    s = cid_src.strip()
    if s.lower().startswith("cid:"):
        s = s[4:].strip()

    s = unquote(s)
    s = s.strip().strip("<>").strip()
    if not s:
        return []

    out = [s, s.lower()]
    if "@" in s:
        base = s.split("@", 1)[0]
        out.extend([base, base.lower()])

    # de-dupe preserving order
    seen = set()
    uniq: list[str] = []
    for x in out:
        if x and x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq

def build_inline_index(atts: Iterable[AttachmentMeta]) -> Dict[str, AttachmentMeta]:
    """
    Index inline-ish image attachments by content_id (+ variants).
    """
    idx: Dict[str, AttachmentMeta] = {}
    for a in atts:
        if not a.content_type.lower().startswith("image/"):
            continue
        # Use your is_inline signal OR content_id presence (both are useful)
        if not (a.is_inline or a.content_id):
            continue

        if a.content_id:
            key = a.content_id.strip().strip("<>").strip()
            for k in _cid_variants(key):
                idx.setdefault(k, a)
    return idx

def inline_cids_as_data_uris(
    *,
    html: str,
    attachment_metas: list[AttachmentMeta],
    fetch_part_bytes,  # callable(part: str) -> bytes
) -> str:
    """
    Rewrite <img src="cid:..."> to data: URIs by fetching the bytes via IMAP.
    """
    if not html or not attachment_metas:
        return html

    idx = build_inline_index(attachment_metas)

    def repl(m: re.Match) -> str:
        prefix, src, suffix = m.group(1), m.group(2), m.group(3)
        if not src.lower().startswith("cid:"):
            return m.group(0)

        hit: Optional[AttachmentMeta] = None
        for k in _cid_variants(src):
            hit = idx.get(k)
            if hit:
                break
        if not hit:
            return m.group(0)

        try:
            data = fetch_part_bytes(hit.part)
        except Exception:
            return m.group(0)

        if not data:
            return m.group(0)

        ctype = (hit.content_type or "application/octet-stream").lower()
        b64 = base64.b64encode(data).decode("ascii")
        data_uri = f"data:{ctype};base64,{b64}"
        return f"{prefix}{data_uri}{suffix}"

    return _IMG_SRC_RE.sub(repl, html)
