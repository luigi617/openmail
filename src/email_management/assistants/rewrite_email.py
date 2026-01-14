from typing import Any, Tuple
from pydantic import BaseModel, Field

from email_management.llm import get_model


REWRITE_EMAIL_PROMPT = """
You are an assistant that rewrites email drafts while preserving the original meaning.

Instructions:
- Rewrite the email using the requested style.
- Preserve all important facts, commitments, and dates.
- Keep the structure of an email (greeting, body, closing) if present.
- Do not add new information that is not implied by the original.
- Do not include any explanation; only output the rewritten email text.

Requested style:
{style}

Original email:
{draft}
"""


class RewriteEmailSchema(BaseModel):
    rewritten_email: str = Field(
        description="The full email text rewritten in the requested style."
    )


def llm_rewrite_email(
    draft_text: str,
    style: str,
    *,
    provider: str,
    model_name: str,
) -> Tuple[str, dict[str, Any]]:
    """
    Rewrite an email draft according to a requested style.
    """
    chain = get_model(provider, model_name, RewriteEmailSchema)
    result, llm_call_info = chain(
        REWRITE_EMAIL_PROMPT.format(
            style=style,
            draft=draft_text,
        )
    )
    return result.rewritten_email, llm_call_info
