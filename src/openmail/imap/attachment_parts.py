# openmail/imap/attachment_parts.py
from __future__ import annotations

import imaplib
from email.parser import BytesParser
from email.policy import default as default_policy
from typing import Optional

from openmail.errors import IMAPError
from openmail.imap.parser import decode_transfer


def fetch_part_bytes(
    conn: imaplib.IMAP4,
    *,
    uid: int,
    part: str,
) -> bytes:
    """
    Fetch a single BODY part and decode it according to its MIME headers'
    Content-Transfer-Encoding.

    This is used for:
      - downloading attachments
      - fetching inline CID images for HTML rewriting
    """
    typ, mime_data = conn.uid("FETCH", str(uid), f"(UID BODY.PEEK[{part}.MIME])")
    if typ != "OK" or not mime_data:
        raise IMAPError(f"FETCH attachment MIME failed uid={uid} part={part}: {mime_data}")

    mime_bytes: Optional[bytes] = None
    for item in mime_data:
        if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], (bytes, bytearray)):
            mime_bytes = bytes(item[1])
            break

    cte = None
    if mime_bytes:
        msg = BytesParser(policy=default_policy).parsebytes(mime_bytes)
        cte = msg.get("Content-Transfer-Encoding")

    typ, body_data = conn.uid("FETCH", str(uid), f"(UID BODY.PEEK[{part}])")
    if typ != "OK" or not body_data:
        raise IMAPError(f"FETCH attachment failed uid={uid} part={part}: {body_data}")

    payload: Optional[bytes] = None
    for item in body_data:
        if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], (bytes, bytearray)):
            payload = bytes(item[1])
            break

    if payload is None:
        raise IMAPError(f"Attachment payload not found uid={uid} part={part}")

    return decode_transfer(payload, cte)
