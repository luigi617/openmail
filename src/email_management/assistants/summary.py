from typing import Any, Dict, Optional, Tuple
from pydantic import BaseModel, Field
from email_management.llm import get_model
from email_management.models import EmailMessage
from email_management.utils import build_email_context


EMAIL_SUMMARY_PROMPT = """
You are an assistant that summarizes emails for a busy user.

Instructions (follow all):
- Summarize the email in 2-4 sentences.
- Capture the main points, action items, and any dates/deadlines.
- Do NOT include any meta commentary, just the summary text.

Email context:
{email_context}
"""



class EmailSummarySchema(BaseModel):
    summary: str = Field(description="A concise summary of a single email.")


def llm_summarize_single_email(
    msg: EmailMessage,
    *,
    provider: str,
    model_name: str,
) -> Tuple[str, Dict[str, Any]]:
    """
    Generate a concise email reply using the LLM pipeline.
    """
    chain = get_model(provider, model_name, EmailSummarySchema)
    email_context = build_email_context(msg)
    result, llm_call_info = chain(
        EMAIL_SUMMARY_PROMPT.format(
            email_context=email_context,
        )
    )
    return result.summary, llm_call_info