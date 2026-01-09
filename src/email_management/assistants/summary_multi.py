from typing import List, Sequence
from pydantic import BaseModel, Field

from email_management.llm import get_model
from email_management.models import EmailMessage
from email_management.utils import build_email_context


EMAIL_MULTI_SUMMARY_PROMPT = """
You are helping a user triage multiple emails.

You will see several emails, each labeled with a UID.

Instructions (follow all):
- Write ONE short paragraph.
- Clearly state which emails are IMPORTANT or URGENT.
- Briefly mention the other emails as less important.
- When referring to an IMPORTANT email, you MUST mention its UID exactly
  as 'UID=<number>' so the UI can link directly to it.
- Keep the paragraph compact and easy to scan.

Emails:
{emails_block}

Return:
{{
    "summary": "<One short paragraph that triages all the emails.>"
}}
"""

class EmailMultiSummarySchema(BaseModel):
    summary: str = Field(description="One paragraph summarizing and prioritizing multiple emails.")


def llm_summarize_many_emails(
    messages: Sequence[EmailMessage],
    *,
    model_path: str,
) -> str:
    """
    Generate a concise email reply using the LLM pipeline.
    """
    chain = get_model(model_path, EmailMultiSummarySchema)

    blocks: List[str] = []
    for msg in messages:
        email_context = build_email_context(msg)
        blocks.append(email_context)

    emails_block = "\n---\n".join(blocks)

    result, llm_call_info = chain(
        EMAIL_MULTI_SUMMARY_PROMPT.format(
            emails_block=emails_block,
        )
    )
    res = result["summary"] if result and "summary" in result else result
    return res, llm_call_info