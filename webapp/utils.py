import base64
import json
import re
from typing import Dict, List, Optional

from fastapi import UploadFile

from openmail.models import Attachment


def encode_cursor(state: dict) -> str:
    raw = json.dumps(state, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

def decode_cursor(cursor: str) -> dict:
    padding = "=" * (-len(cursor) % 4)
    raw = base64.urlsafe_b64decode(cursor + padding)
    return json.loads(raw)

async def uploadfiles_to_attachments(
    files: List[UploadFile],
) -> List[Attachment]:
    attachments: List[Attachment] = []
    for f in files:
        if f.filename is None:
            continue
        data = await f.read()
        attachments.append(
            Attachment(
                idx=1,
                part="",
                filename=f.filename,
                content_type=f.content_type or "application/octet-stream",
                data=data,
                size=len(data),
            )
        )
    return attachments

def build_extra_headers(
    reply_to: Optional[List[str]],
    priority: Optional[str],
) -> Dict[str, str]:
    headers: Dict[str, str] = {}

    if reply_to:
        headers["Reply-To"] = ", ".join(reply_to)

    if priority:
        p = priority.lower()
        if p == "high":
            headers.update(
                {
                    "X-Priority": "1 (Highest)",
                    "X-MSMail-Priority": "High",
                    "Importance": "High",
                }
            )
        elif p == "low":
            headers.update(
                {
                    "X-Priority": "5 (Lowest)",
                    "X-MSMail-Priority": "Low",
                    "Importance": "Low",
                }
            )

    return headers

def safe_filename(name: str, fallback: str = "attachment.bin") -> str:
    if not name:
        return fallback
    name = name.strip().replace("\\", "_").replace("/", "_")
    name = re.sub(r"[\x00-\x1f\x7f]+", "", name)
    return name or fallback