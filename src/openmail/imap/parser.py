from __future__ import annotations

import base64
import email
import quopri
from datetime import datetime
from email import policy
from email.header import decode_header, make_header
from email.message import Message as PyMessage
from email.parser import BytesParser
from email.policy import default as default_policy
from email.utils import getaddresses
from typing import Dict, List, Optional, Tuple

from openmail.errors import ParseError
from openmail.models import Attachment, EmailAddress, EmailMessage, EmailOverview
from openmail.types import EmailRef
from openmail.utils import best_effort_date

_INTERNALDATE_FMTS = [
    "%d-%b-%Y %H:%M:%S %z",  # standard INTERNALDATE
]

def parse_internaldate(internaldate_raw: Optional[str]) -> Optional[datetime]:
    if not internaldate_raw:
        return None
    s = internaldate_raw.strip().strip('"')
    for fmt in _INTERNALDATE_FMTS:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None

def _decode_header_value(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def decode_transfer(payload: bytes, cte: str | None) -> bytes:
    if not cte:
        return payload
    cte = cte.strip().lower()

    if cte == "base64":
        return base64.b64decode(payload, validate=False)
    if cte in ("quoted-printable", "quopri"):
        return quopri.decodestring(payload)
    return payload


def decode_body_chunk(chunk: bytes, msg: PyMessage) -> str:
    """
    Decode a body chunk using Content-Transfer-Encoding and charset
    from the given (headers-only) message.
    """
    charset = msg.get_content_charset() or "utf-8"
    cte = (msg.get("Content-Transfer-Encoding") or "").lower()

    raw = chunk
    try:
        if cte == "base64":
            raw = base64.b64decode(raw, validate=False)
        elif cte in ("quoted-printable", "quotedprintable"):
            raw = quopri.decodestring(raw)
    except Exception:
        raw = chunk

    try:
        return raw.decode(charset, errors="replace")
    except Exception:
        return raw.decode("utf-8", errors="replace")


def _parse_addr_list(header_val: Optional[str]) -> List[EmailAddress]:
    if not header_val:
        return []
    out: List[EmailAddress] = []
    for name, addr in getaddresses([header_val]):
        name_decoded = _decode_header_value(name).strip()
        addr = (addr or "").strip()
        if not addr and not name_decoded:
            continue
        out.append(EmailAddress(email=addr or "", name=name_decoded or None))
    return out


def _parse_single_addr(header_val: Optional[str]) -> EmailAddress:
    addrs = _parse_addr_list(header_val)
    return addrs[0] if addrs else EmailAddress(email="", name=None)


def _extract_parts(msg: PyMessage) -> Tuple[Optional[str], Optional[str], List[Attachment]]:
    text: Optional[str] = None
    html: Optional[str] = None
    atts: List[Attachment] = []
    attachment_idx = 0

    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue

            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()

            filename = part.get_filename()
            if filename:
                filename = _decode_header_value(filename)

            payload = part.get_payload(decode=True) or b""

            content_id = part.get("Content-ID")
            if content_id:
                content_id = content_id.strip().strip("<>").strip() or None

            is_inline_image = (
                ctype.startswith("image/")
                and (("inline" in disp) or bool(content_id))
            )

            # Attachment (explicit disposition or filename)
            if filename or "attachment" in disp:
                atts.append(
                    Attachment(
                        idx=attachment_idx,
                        filename=filename or "attachment",
                        content_type=ctype,
                        data=payload,
                        size=len(payload),
                        content_id=content_id,
                        disposition=("inline" if is_inline_image else ("attachment" if "attachment" in disp else None)),
                        is_inline=is_inline_image,
                    )
                )
                attachment_idx += 1
                continue

            if ctype in ("text/plain", "text/html"):
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


def decode_section(mime_bytes: Optional[bytes], body_bytes: Optional[bytes]) -> str:
    if not body_bytes:
        return ""
    if not mime_bytes:
        try:
            return body_bytes.decode("utf-8", errors="replace")
        except Exception:
            return body_bytes.decode("latin-1", errors="replace")

    msg = BytesParser(policy=default_policy).parsebytes(mime_bytes)
    return decode_body_chunk(body_bytes, msg)


def parse_rfc822(
    ref: EmailRef,
    raw: bytes,
    *,
    include_attachments: bool = False,
    internaldate_raw: Optional[str] = None,
) -> EmailMessage:
    try:
        pymsg: PyMessage = email.message_from_bytes(raw, policy=policy.default)

        text, html, atts = _extract_parts(pymsg)
        if not include_attachments:
            atts = []

        headers: Dict[str, str] = {k: _decode_header_value(str(v)) for k, v in pymsg.items()}

        raw_date = pymsg.get("Date")
        received_at = parse_internaldate(internaldate_raw)
        sent_at = best_effort_date(raw_date, None)

        return EmailMessage(
            ref=ref,
            subject=_decode_header_value(pymsg.get("Subject")),
            from_email=_parse_single_addr(pymsg.get("From")),
            to=_parse_addr_list(pymsg.get("To")),
            cc=_parse_addr_list(pymsg.get("Cc")),
            bcc=_parse_addr_list(pymsg.get("Bcc")),
            text=text,
            html=html,
            attachments=atts,
            received_at=received_at,
            sent_at=sent_at,
            message_id=_decode_header_value(pymsg.get("Message-ID")),
            headers=headers,
        )
    except Exception as e:
        raise ParseError(f"Failed to parse RFC822: {e}") from e


def parse_headers_and_bodies(
    ref: EmailRef,
    header_bytes: bytes,
    *,
    text: str,
    html: str,
    attachments,
    internaldate_raw: Optional[str] = None,
) -> EmailMessage:
    try:
        msg_headers = BytesParser(policy=default_policy).parsebytes(header_bytes or b"")

        headers: Dict[str, str] = {k: _decode_header_value(str(v)) for k, v in msg_headers.items()}
        raw_date = msg_headers.get("Date")
        received_at = parse_internaldate(internaldate_raw)
        sent_at = best_effort_date(raw_date, None)

        return EmailMessage(
            ref=ref,
            subject=_decode_header_value(msg_headers.get("Subject")),
            from_email=_parse_single_addr(msg_headers.get("From")),
            to=_parse_addr_list(msg_headers.get("To")),
            cc=_parse_addr_list(msg_headers.get("Cc")),
            bcc=_parse_addr_list(msg_headers.get("Bcc")),
            text=text or None,
            html=html or None,
            attachments=attachments,
            received_at=received_at,
            sent_at=sent_at,
            message_id=_decode_header_value(msg_headers.get("Message-ID")),
            headers=headers,
        )
    except Exception as e:
        raise ParseError(f"Failed to parse headers/bodies: {e}") from e


def parse_overview(
    ref: EmailRef,
    flags: set,
    header_bytes: bytes | bytearray,
    *,
    internaldate_raw: Optional[str] = None,
) -> EmailOverview:
    try:
        subject = ""
        from_addr = EmailAddress(email="", name=None)
        to_addrs: List[EmailAddress] = []
        headers: Dict[str, str] = {}
        date_header_raw: Optional[str] = None

        if isinstance(header_bytes, (bytes, bytearray)):
            msg_headers = BytesParser(policy=default_policy).parsebytes(bytes(header_bytes))

            subject = _decode_header_value(msg_headers.get("Subject"))
            from_addr = _parse_single_addr(msg_headers.get("From"))
            date_header_raw = msg_headers.get("Date")

            to_raw_list = msg_headers.get_all("To", [])
            if to_raw_list:
                to_addrs = _parse_addr_list(", ".join(to_raw_list))

            for k, v in msg_headers.items():
                headers[k] = _decode_header_value(str(v))

        received_at = parse_internaldate(internaldate_raw)
        sent_at = best_effort_date(date_header_raw, None)


        return EmailOverview(
            ref=ref,
            subject=subject or "",
            from_email=from_addr or EmailAddress(email="", name=None),
            to=to_addrs,
            flags=flags,
            received_at=received_at,
            sent_at=sent_at,
            headers=headers,
        )
    except Exception as e:
        raise ParseError(f"Failed to parse Email Overview: {e}") from e
