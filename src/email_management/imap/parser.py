from __future__ import annotations

import email
from email import policy
from email.header import decode_header, make_header
from email.message import Message as PyMessage
from email.utils import getaddresses
from typing import Optional, Tuple, List, Dict

from email_management.models import EmailMessage, Attachment
from email_management.errors import ParseError
from email_management.types import EmailRef


def _decode(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        # Fallback: return raw value if decoding fails
        return value


def _parse_addr_list(header_val: Optional[str]) -> List[str]:
    """
    Turn a header like:
      'Alice <a@x.com>, "Bob B" <b@y.com>'
    into:
      ['Alice <a@x.com>', 'Bob B <b@y.com>']  (or bare emails if no name)
    """
    if not header_val:
        return []
    out: List[str] = []
    for name, addr in getaddresses([header_val]):
        name = _decode(name).strip()
        addr = (addr or "").strip()
        if not addr and not name:
            continue
        if addr and name:
            out.append(f"{name} <{addr}>")
        else:
            out.append(addr or name)
    return out


def _extract_parts(msg: PyMessage) -> Tuple[Optional[str], Optional[str], List[Attachment]]:
    text: Optional[str] = None
    html: Optional[str] = None
    atts: List[Attachment] = []

    if msg.is_multipart():
        for part in msg.walk():
            # Skip container parts
            if part.is_multipart():
                continue

            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()
            filename = part.get_filename()
            if filename:
                filename = _decode(filename)

            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"

            # Attachment (explicit disposition or filename)
            if filename or "attachment" in disp:
                atts.append(Attachment(filename or "attachment", ctype, payload))
                continue

            # Body parts
            if ctype == "text/plain" and text is None:
                text = payload.decode(charset, errors="replace")
            elif ctype == "text/html" and html is None:
                html = payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        body = payload.decode(charset, errors="replace")
        if msg.get_content_type() == "text/html":
            html = body
        else:
            text = body

    return text, html, atts


def parse_rfc822(ref: EmailRef, raw: bytes, *, include_attachments: bool = False) -> EmailMessage:
    try:
        # Use modern policy for better Unicode/structured header handling
        pymsg: PyMessage = email.message_from_bytes(raw, policy=policy.default)

        text, html, atts = _extract_parts(pymsg)
        if not include_attachments:
            atts = []

        # Capture all headers so future features can use them
        headers: Dict[str, str] = {k: _decode(str(v)) for k, v in pymsg.items()}

        return EmailMessage(
            ref=ref,
            subject=_decode(pymsg.get("Subject")),
            from_email=_decode(pymsg.get("From")),
            to=_parse_addr_list(pymsg.get("To")),
            cc=_parse_addr_list(pymsg.get("Cc")),
            bcc=_parse_addr_list(pymsg.get("Bcc")),
            text=text,
            html=html,
            attachments=atts,
            message_id=_decode(pymsg.get("Message-ID")),
            headers=headers,
        )
    except Exception as e:
        raise ParseError(f"Failed to parse RFC822: {e}") from e
