from pydantic import BaseModel, Field
from email_management.llm import get_model
from email_management.models import EmailMessage
from email_management.utils import build_email_context


EMAIL_REPLY_PROMPT = """
You are an assistant that drafts concise, polite email replies.

Instructions (follow all):
- Write a direct reply to the email content.
- Be professional but friendly.
- Keep it short and to the point.
- Do NOT explain what you are doing.
- Output ONLY the email reply body text (no surrounding quotes).

Email context:
{email_context}

Return:
{{
    "reply": "<The generated reply body.>"
}}
"""

class EmailReplySchema(BaseModel):
    reply: str = Field(description="A concise reply body for the email.")


def llm_concise_reply_for_email(
    msg: EmailMessage,
    *,
    model_path: str,
) -> str:
    """
    Generate a concise email reply using the LLM pipeline.
    """
    chain = get_model(model_path, EmailReplySchema)
    email_context = build_email_context(msg)
    result, llm_call_info = chain(
        EMAIL_REPLY_PROMPT.format(
            email_context=email_context,
        )
    )
    res = result["reply"] if result and "reply" in result else result
    return res, llm_call_info