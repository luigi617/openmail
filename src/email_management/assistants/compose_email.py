from __future__ import annotations
from typing import Any, Tuple
from pydantic import BaseModel, Field
from email_management.llm import get_model

COMPOSE_EMAIL_PROMPT = """
You are an assistant that drafts professional emails.

Instructions:
- Use clear, concise, professional language unless told otherwise.
- Provide both a subject line and a body.
- Do not include quotes or commentary about the email.
- The body should be ready to send as-is (no placeholders like [NAME]).
- Avoid overly flowery language.

User instructions:
{instructions}
"""

class ComposeEmailSchema(BaseModel):
    subject: str = Field(description="Subject line for the email.")
    body: str = Field(description="Full email body, ready to send.")

def llm_compose_email(
    instructions: str,
    *,
    provider: str,
    model_name: str,
) -> Tuple[str, str, dict[str, Any]]:
    """
    Compose a new email from natural-language instructions.
    """
    chain = get_model(provider, model_name, ComposeEmailSchema)
    result, llm_call_info = chain(
        COMPOSE_EMAIL_PROMPT.format(instructions=instructions)
    )

    subject = result.subject.strip()
    body = result.body.strip()
    return subject, body, llm_call_info
