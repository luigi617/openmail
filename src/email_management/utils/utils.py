import html as _html
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage as PyEmailMessage
from email.utils import getaddresses, formataddr
from typing import Optional, Sequence, Dict, Any, Set, Tuple, List

from email_management.models import EmailMessage
from email_management.types import EmailRef


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

def quote_original_text(original: EmailMessage) -> str:
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

def quote_original_html(original: EmailMessage) -> str:
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
