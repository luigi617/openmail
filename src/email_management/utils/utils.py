import html as _html
from datetime import datetime, timezone, timedelta
from email.utils import getaddresses, formataddr, parsedate_to_datetime
import re
from typing import Optional, Dict, List

from email_management.models import EmailMessage


def iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()

def ensure_forward_subject(subject: str) -> str:
    """
    Ensure the subject is prefixed with 'Fwd:' (or 'Fw:') exactly once.
    """
    if not subject:
        return "Fwd:"
    lower = subject.lower()
    if lower.startswith("fwd:") or lower.startswith("fw:"):
        return subject
    return f"Fwd: {subject}"

def ensure_reply_subject(subj: Optional[str]) -> str:
    if not subj:
        return "Re:"
    s = subj.strip()
    if s.lower().startswith("re:"):
        return subj
    return f"Re: {subj}"

def parse_addrs(*values: Optional[str]) -> List[tuple[str, str]]:
    out: List[tuple[str, str]] = []
    for v in values:
        if v:
            out.extend(getaddresses([v]))
    return out

def dedup_addrs(pairs: List[tuple[str, str]]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for name, addr in pairs:
        addr_norm = addr.strip().lower()
        if not addr_norm or addr_norm in seen:
            continue
        seen.add(addr_norm)
        result.append(formataddr((name, addr)) if name else addr)
    return result

def remove_addr(pairs: List[tuple[str, str]], remove: Optional[str]) -> List[tuple[str, str]]:
    if not remove:
        return pairs
    rm_norm = remove.strip().lower()
    return [(n, a) for (n, a) in pairs if a.strip().lower() != rm_norm]

def get_header(headers: Dict[str, str], key: str) -> Optional[str]:
    """Case-insensitive header lookup from EmailMessage.headers."""
    key_lower = key.lower()
    for k, v in headers.items():
        if k.lower() == key_lower:
            return v
    return None

def build_references(existing_refs: Optional[str], orig_mid: str) -> str:
    if not existing_refs:
        return orig_mid
    if orig_mid in existing_refs:
        return existing_refs
    return f"{existing_refs} {orig_mid}"

def build_email_context(msg: EmailMessage) -> str:
    """
    Build a text block representing one email for prompts.
    """
    subject = msg.subject
    from_addr = msg.from_email
    date = msg.date
    body = msg.text

    date_part = f"Date: {date}\n" if date else ""

    return (
        f"From: {from_addr}\n"
        f"Subject: {subject}\n"
        f"{date_part}"
        f"Body:\n{body}\n"
    )

def quote_original_reply_text(original: EmailMessage) -> str:
    """
    Build a plain-text quoted block of the original email, e.g.:

    On 2026-01-12T10:00:00+00:00, alice@example.com wrote:
    > line 1
    > line 2
    """
    if original.date:
        date_str = original.date.isoformat()
    else:
        date_str = "an earlier date"

    header = f"On {date_str}, {original.from_email} wrote:"

    # Body to quote
    body = original.text or ""
    if not body and original.html:
        body = "[original HTML body omitted]"

    quoted_body_lines = [f"> {line}" for line in body.splitlines()] if body else []
    return "\n".join([header, *quoted_body_lines])

def quote_original_reply_html(original: EmailMessage) -> str:
    """
    Build an HTML quoted block of the original email.

    Uses <blockquote> for the body, and a short 'On ..., X wrote:' header.
    """
    if original.date:
        date_str = original.date.isoformat()
    else:
        date_str = "an earlier date"

    header_html = (
        f"On {_html.escape(date_str)}, "
        f"{_html.escape(original.from_email)} wrote:"
    )

    if original.html:
        body_html = f"<blockquote>{original.html}</blockquote>"
    elif original.text:
        body_html = (
            "<blockquote><pre>"
            + _html.escape(original.text)
            + "</pre></blockquote>"
        )
    else:
        body_html = "<blockquote><em>(no body)</em></blockquote>"

    return f"<p>{header_html}</p>\n{body_html}"

def quote_forward_text(original: EmailMessage) -> str:
    """
    Build the quoted plain text block for a forwarded message.
    """
    quoted_lines: List[str] = []
    quoted_lines.append("")
    quoted_lines.append("---- Forwarded message ----")
    quoted_lines.append(f"From: {original.from_email}")
    if original.to:
        quoted_lines.append(f"To: {', '.join(original.to)}")
    if original.cc:
        quoted_lines.append(f"Cc: {', '.join(original.cc)}")
    if original.date:
        quoted_lines.append(f"Date: {original.date.isoformat()}")
    if original.subject:
        quoted_lines.append(f"Subject: {original.subject}")
    quoted_lines.append("")
    if original.text:
        quoted_lines.append(original.text)

    return "\n".join(quoted_lines)

def quote_forward_html(original: EmailMessage) -> Optional[str]:
    """
    Build the quoted HTML block for a forwarded message.
    """

    if not (original.html or original.text):
        return None

    html_parts: List[str] = []

    html_parts.append("<hr>")
    html_parts.append("<p>---- Forwarded message ----</p>")

    header_lines: List[str] = []
    header_lines.append(f"From: {original.from_email}")
    if original.to:
        header_lines.append(f"To: {', '.join(original.to)}")
    if original.cc:
        header_lines.append(f"Cc: {', '.join(original.cc)}")
    if original.date:
        header_lines.append(f"Date: {original.date.isoformat()}")
    if original.subject:
        header_lines.append(f"Subject: {original.subject}")

    header_html = "<br>".join(_html.escape(line) for line in header_lines)
    html_parts.append(f"<p>{header_html}</p>")

    if original.html:
        html_parts.append(original.html)
    else:
        html_parts.append("<pre>" + _html.escape(original.text or "") + "</pre>")

    return "\n".join(html_parts)

def parse_list_mailbox_name(raw: bytes | str) -> str | None:
        """
        Parse a single IMAP LIST response line and extract the mailbox name.
        Handles typical formats like:
            (\\HasNoChildren) "/" "INBOX"
            (\\Noselect) "/" "[Gmail]/All Mail"
            (\\HasNoChildren) "/" INBOX
        Returns the decoded mailbox name or None if it can't be parsed.
        """
        if isinstance(raw, bytes):
            s = raw.decode(errors="ignore")
        else:
            s = str(raw)

        s = s.strip()

        m = re.match(r'\((?P<flags>.*?)\)\s+(?P<delim>NIL|".*?"|\S+)\s+(?P<name>.+)', s)
        if not m:
            return None

        name = m.group("name").strip()

        if name.startswith('"') and name.endswith('"'):
            name = name[1:-1]

        try:
            from imaplib import _decode_utf7 as decode_utf7  # type: ignore[attr-defined]
            name = decode_utf7(name)
        except Exception:
            pass

        return name or None

def safe_decode(data: bytes) -> Optional[str]:
    """
    Try UTF-8 decode, fallback to latin-1.
    Returns decoded string or None if decoding fails.
    """
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("latin-1")
        except Exception:
            return None
        
def looks_binary(text: str) -> bool:
    """
    Heuristic to detect binary-like decoded content.
    If >30% of characters are control chars or weird unicode blocks.
    """
    if not text:
        return False
    control_chars = sum(ch < " " for ch in text)
    return (control_chars / len(text)) > 0.3

def best_effort_date(date_header: str | None,
                      internaldate_raw: str | None) -> datetime | None:
    """
    Pick the best possible date for an email, trying:
    1. Header Date
    2. IMAP INTERNALDATE
    """

    def _parse_one(raw: str | None) -> datetime | None:
        if not raw:
            return None
        try:
            dt = parsedate_to_datetime(raw)
            if dt is None:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except (TypeError, ValueError, OverflowError):
            return None

    header_dt = _parse_one(date_header)
    internal_dt = _parse_one(internaldate_raw)

    # Prefer header date if it looks sane
    if header_dt is not None:
        earliest = datetime(1970, 1, 1, tzinfo=timezone.utc)
        latest = datetime.now(timezone.utc) + timedelta(days=1)
        if earliest <= header_dt <= latest:
            return header_dt

    if internal_dt is not None:
        return internal_dt

    return None

