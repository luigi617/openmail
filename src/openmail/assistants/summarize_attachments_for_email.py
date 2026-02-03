from __future__ import annotations

from typing import Any, Dict, List, Tuple

from pydantic import BaseModel, Field

from openmail.llm import get_model
from openmail.models import EmailMessage
from openmail.utils import looks_binary, safe_decode

ATTACHMENT_SUMMARY_PROMPT = """
You are an assistant that summarizes file attachments from an email.

Instructions:
- For each attachment, provide a concise summary (3-6 sentences).
- Focus on key points, decisions, and any important data.
- Do not copy large passages verbatim.
- If the content is not meaningful (e.g. very short or empty), say so briefly.

Below are the attachments with their content.

Attachments:
{attachments_context}
"""

class AttachmentSummarySchema(BaseModel):
    filename: str = Field(description="Filename of the attachment.")
    summary: str = Field(description="Concise summary of the attachment's contents.")


class AttachmentSummariesSchema(BaseModel):
    attachments: List[AttachmentSummarySchema] = Field(
        description="List of summaries for each attachment."
    )

def _build_attachments_context(message: EmailMessage) -> str:
    """
    Build a text context representing all attachments.

    Adjust attribute names here to match your actual attachment model.
    """
    
    attachments = message.attachments
    parts: List[str] = []

    for idx, att in enumerate(attachments, start=1):
        filename = att.filename
        # Try common attributes for text content
        data = att.data
        decoded = safe_decode(data)

        if not decoded:
            parts.append(
                f"--- Attachment #{idx} ---\n"
                f"Filename: {filename}\n"
                f"Content: [non-text or empty bytes]\n"
            )
            continue

        if looks_binary(decoded):
            parts.append(
                f"--- Attachment #{idx} ---\n"
                f"Filename: {filename}\n"
                f"Content: [binary data - not summarized]\n"
            )
            continue

        if len(decoded) > 4000:
            decoded = decoded[:4000] + "\n...[truncated]..."

        parts.append(
            f"--- Attachment #{idx} ---\n"
            f"Filename: {filename}\n"
            f"Content:\n{decoded}\n"
        )

    return "\n".join(parts)


def llm_summarize_attachments_for_email(
    message: EmailMessage,
    *,
    provider: str,
    model_name: str,
) -> Tuple[Dict[str, str], dict[str, Any]]:
    """
    Summarize each attachment in an email.
    """
    attachments = message.attachments
    if not attachments:
        return {}, {}

    attachments_context = _build_attachments_context(message)

    chain = get_model(provider, model_name, AttachmentSummariesSchema)
    result, llm_call_info = chain(
        ATTACHMENT_SUMMARY_PROMPT.format(attachments_context=attachments_context)
    )

    summaries: Dict[str, str] = {
        att.filename: att.summary for att in result.attachments
    }
    return summaries, llm_call_info
