from typing import Any, Tuple
from pydantic import BaseModel, Field

from email_management.llm import get_model
from email_management.models import EmailMessage
from email_management.utils import build_email_context


SENDER_TRUST_PROMPT = """
You are an assistant that estimates how trustworthy the sender of an email appears.

Consider:
- Sender address and domain (well-known company, free email provider, random domain, etc.).
- Consistency between display name and email address.
- Professionalism and clarity of the writing.
- Whether the content matches what you would expect from a legit sender.
- Obvious red flags (phishing patterns, strange requests, etc.).

Instructions:
- Output a trust_score between 0.0 and 1.0:
  - 1.0 = highly trustworthy (e.g., known and legitimate sender, no red flags).
  - 0.0 = highly untrustworthy (e.g., obvious scam).
- Base your judgement entirely on the email context provided.
- Briefly explain your reasoning.

Email context:
{email_context}
"""


class SenderTrustSchema(BaseModel):
    trust_score: float = Field(
        ge=0.0,
        le=1.0,
        description="How trustworthy the sender appears, between 0.0 (untrustworthy) and 1.0 (highly trustworthy).",
    )
    reasoning: str = Field(
        description="Short explanation for the chosen trust_score."
    )


def llm_evaluate_sender_trust_for_email(
    msg: EmailMessage,
    *,
    model_path: str,
) -> Tuple[float, dict[str, Any]]:
    """
    Evaluate how trustworthy the sender appears based on the email.
    """
    chain = get_model(model_path, SenderTrustSchema)
    email_context = build_email_context(msg)

    prompt = SENDER_TRUST_PROMPT.format(
        email_context=email_context,
    )

    result, llm_call_info = chain(prompt)
    return result.trust_score, llm_call_info
