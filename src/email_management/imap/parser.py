from __future__ import annotations

import email
import base64
import quopri
from email import policy
from email.header import decode_header, make_header
from email.message import Message as PyMessage
from email.parser import BytesParser
from email.utils import getaddresses
from email.policy import default as default_policy
from typing import Optional, Tuple, List, Dict

from email_management.models import EmailAddress, EmailMessage, Attachment, EmailOverview
from email_management.errors import ParseError
from email_management.types import EmailRef
from email_management.utils import best_effort_date


def _decode(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value
    
def _decode_body_chunk(chunk: bytes, msg: PyMessage) -> str:
    """
    Decode a body chunk using Content-Transfer-Encoding and charset
    from the given (headers-only) message.
    Mirrors what get_payload(decode=True) + charset decode would do.
    """
    # Charset from Content-Type
    charset = msg.get_content_charset() or "utf-8"
    cte = (msg.get("Content-Transfer-Encoding") or "").lower()

    raw = chunk

    # 1) Decode transfer encoding (base64 / quoted-printable)
    try:
        if cte == "base64":
            raw = base64.b64decode(raw, validate=False)
        elif cte in ("quoted-printable", "quotedprintable"):
            raw = quopri.decodestring(raw)
    except Exception:
        # if decoding fails, fall back to original
        raw = chunk

    # 2) Decode bytes → str using charset
    try:
        return raw.decode(charset, errors="replace")
    except Exception:
        return raw.decode("utf-8", errors="replace")


def _parse_addr_list(header_val: Optional[str]) -> List[EmailAddress]:
    if not header_val:
        return []
    out: List[EmailAddress] = []
    for name, addr in getaddresses([header_val]):
        name_decoded = _decode(name).strip()
        addr = (addr or "").strip()
        if not addr and not name_decoded:
            continue
        # If there's no addr, but there is a name, we still want *something*
        email_value = addr or ""
        name_value = name_decoded or None
        out.append(EmailAddress(email=email_value, name=name_value))
    return out

def _parse_single_addr(header_val: Optional[str]) -> EmailAddress:
    """
    Parse a single-address header (e.g. From).
    If multiple addresses exist, returns the first.
    If missing/invalid, returns an empty EmailAddress.
    """
    addrs = _parse_addr_list(header_val)
    if addrs:
        return addrs[0]
    return EmailAddress(email="", name=None)

def _extract_parts(msg: PyMessage) -> Tuple[Optional[str], Optional[str], List[Attachment]]:
    text: Optional[str] = None
    html: Optional[str] = None
    atts: List[Attachment] = []
    
    attachment_idx = 0
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

            # Attachment (explicit disposition or filename)
            if filename or "attachment" in disp:
                atts.append(Attachment(
                    id=attachment_idx,
                    filename=filename or "attachment",
                    content_type=ctype,
                    data=payload,
                    data_size=len(payload),
                ))
                attachment_idx += 1
                continue
            if ctype in ("text/plain", "text/html"):
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                body = payload.decode(charset, errors="replace")

                if ctype == "text/plain" and text is None:
                    text = body
                elif ctype == "text/html" and html is None:
                    html = body
    else:
        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        body = payload.decode(charset, errors="replace")

        if msg.get_content_type() == "text/html":
            html = body
        else:
            text = body

    return text, html, atts


def parse_rfc822(
        ref: EmailRef,
        raw: bytes,
        *,
        include_attachments: bool = False,
        internaldate_raw: Optional[str] = None,
    ) -> EmailMessage:
    try:
        # Use modern policy for better Unicode/structured header handling
        pymsg: PyMessage = email.message_from_bytes(raw, policy=policy.default)

        text, html, atts = _extract_parts(pymsg)
        if not include_attachments:
            atts = []

        # Capture all headers so future features can use them
        headers: Dict[str, str] = {k: _decode(str(v)) for k, v in pymsg.items()}

        raw_date = pymsg.get("Date")
        msg_date = best_effort_date(raw_date, internaldate_raw)

        return EmailMessage(
            ref=ref,
            subject=_decode(pymsg.get("Subject")),
            from_email=_parse_single_addr(pymsg.get("From")),
            to=_parse_addr_list(pymsg.get("To")),
            cc=_parse_addr_list(pymsg.get("Cc")),
            bcc=_parse_addr_list(pymsg.get("Bcc")),
            text=text,
            html=html,
            attachments=atts,
            date=msg_date,
            message_id=_decode(pymsg.get("Message-ID")),
            headers=headers,
        )
    except Exception as e:
        raise ParseError(f"Failed to parse RFC822: {e}") from e
    

def parse_overview(
        ref: EmailRef,
        flags: set,
        header_bytes: bytes | bytearray,
        *,
        internaldate_raw: Optional[str] = None,
    ) -> EmailMessage:
    try:
        subject = None
        from_addr = EmailAddress(email="", name=None)
        to_addrs: List[str] = []
        headers: Dict[str, str] = {}
        date_header_raw = None
        msg_headers: Optional[PyMessage] = None

        if isinstance(header_bytes, (bytes, bytearray)):
            msg_headers = BytesParser(policy=default_policy).parsebytes(header_bytes)

            subject = _decode(msg_headers.get("Subject"))
            from_addr = _parse_single_addr(msg_headers.get("From"))
            date_header_raw = msg_headers.get("Date")

            to_raw_list = msg_headers.get_all("To", [])
            if to_raw_list:
                to_combined = ", ".join(to_raw_list)
                to_addrs = _parse_addr_list(to_combined)

            # Copy headers (decoded) into a dict
            for k, v in msg_headers.items():
                headers[k] = _decode(str(v))

        date = best_effort_date(date_header_raw, internaldate_raw)

        subject_final = subject or ""
        from_final = from_addr or EmailAddress(email="", name=None)

        return EmailOverview(
                ref=ref,
                subject=subject_final,
                from_email=from_final,
                to=to_addrs,
                flags=flags,
                date=date,
                headers=headers,
            )
                
    except Exception as e:
        raise ParseError(f"Failed to parse Email Overview: {e}") from e
