from __future__ import annotations
from typing import Any, Tuple, List
from pydantic import BaseModel, Field
from email_management.llm import get_model
from email_management.models import EmailMessage
from email_management.utils import build_email_context


EMAIL_REPLY_SUGGESTION_PROMPT = """
You are an assistant that generates brief suggestions for how a user could reply to an email.

Instructions:
- Provide 2 to 3 distinct reply strategies.
- Each suggestion must be short (4 to 10 words).
- Describe the intent of the reply, NOT the reply text itself.
- No numbering, no bullets, no quotes, no commentary.
- Separate each suggestion with a blank line.

Email context:
{email_context}
"""

class EmailReplySuggestionsSchema(BaseModel):
    suggestions: List[str] = Field(
        description="2-3 concise suggestions describing how to reply."
    )


def llm_reply_suggestions_for_email(
    msg: EmailMessage,
    *,
    provider: str,
    model_name: str,
) -> Tuple[List[str], dict[str, Any]]:
    """
    Generate 2-3 short reply suggestions using the LLM pipeline.
    """
    chain = get_model(provider, model_name, EmailReplySuggestionsSchema)
    email_context = build_email_context(msg)
    result, llm_call_info = chain(
        EMAIL_REPLY_SUGGESTION_PROMPT.format(
            email_context=email_context,
        )
    )
    return result.suggestions, llm_call_info
