from __future__ import annotations

from typing import Any, Tuple

from pydantic import BaseModel, Field

from openmail.llm import get_model
from openmail.models import EmailMessage
from openmail.utils import build_email_context

FOLLOW_UP_PROMPT = """
You are an assistant that writes a polite, concise follow-up email.

Context:
- The user previously sent or received the email shown below.
- They now want to send a follow-up because there has been no response or progress.

Instructions:
- Write a short, natural follow-up email body.
- Keep it polite and professional.
- Briefly reference the previous message.
- Ask for an update or next steps.
- Do NOT include a subject line.
- Do NOT add salutations like "From:". Only include the email body content.

Email context:
{email_context}
"""


class FollowUpEmailSchema(BaseModel):
    follow_up_body: str = Field(
        description="A concise, polite follow-up email body text with no subject line."
    )


def llm_generate_follow_up_for_email(
    msg: EmailMessage,
    *,
    provider: str,
    model_name: str,
) -> Tuple[str, dict[str, Any]]:
    """
    Generate a follow-up email body for a previous message.
    """
    chain = get_model(provider, model_name, FollowUpEmailSchema)
    email_context = build_email_context(msg)

    prompt = FOLLOW_UP_PROMPT.format(
        email_context=email_context,
    )

    result, llm_call_info = chain(prompt)
    return result.follow_up_body, llm_call_info
