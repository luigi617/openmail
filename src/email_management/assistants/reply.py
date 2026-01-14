from typing import Any, Optional, Tuple
from pydantic import BaseModel, Field
from email_management.llm import get_model
from email_management.models import EmailMessage
from email_management.utils import build_email_context


EMAIL_REPLY_PROMPT = """
You are an assistant that drafts concise, polite email replies.

The previous suggested reply (for reference or editing):
{previous_reply}

The user's instruction about how to change or generate the reply:
{reply_context}

Instructions (follow all):
- Either improve/refine the previous reply, or write a new one if needed.
- Follow the user's instruction above as much as possible.
- Be professional but friendly.
- Keep it short and to the point.
- Do NOT explain what you are doing.
- Output ONLY the email reply body text (no surrounding quotes).

Email context:
{email_context}
"""

class EmailReplySchema(BaseModel):
    reply: str = Field(description="A concise reply body for the email.")


def llm_concise_reply_for_email(
    reply_context: str,
    msg: EmailMessage,
    *,
    provider: str,
    model_name: str,
    previous_reply: Optional[str] = None,
) -> Tuple[str, dict[str, Any]]:
    """
    Generate a concise email reply using the LLM pipeline.
    """
    chain = get_model(provider, model_name, EmailReplySchema)
    email_context = build_email_context(msg)
    result, llm_call_info = chain(
        EMAIL_REPLY_PROMPT.format(
            previous_reply=previous_reply or "",
            reply_context=reply_context,
            email_context=email_context,
        )
    )

    return result.reply, llm_call_info