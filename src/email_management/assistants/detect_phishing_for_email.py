from __future__ import annotations
from typing import Any, Tuple
from pydantic import BaseModel, Field
from email_management.llm import get_model
from email_management.models import EmailMessage
from email_management.utils import build_email_context


PHISHING_DETECTION_PROMPT = """
You are a security assistant that determines whether an email is likely to be a phishing or scam attempt.

Consider:
- Suspicious links or requests (passwords, bank details, crypto, gift cards, etc.).
- Urgency or threats designed to pressure the user.
- Mismatched or spoofed sender names/domains.
- Poor grammar or odd phrasing typical of scams.
- Unsolicited attachments or requests to open files.

Instructions:
- Set is_phishing = true if the email is likely to be phishing or a scam.
- Otherwise, set is_phishing = false.
- Provide a confidence score between 0.0 and 1.0.
- Briefly explain your reasoning referencing specific aspects of the email.

Email context:
{email_context}
"""

class PhishingDetectionSchema(BaseModel):
    is_phishing: bool = Field(
        description="True if the email is likely a phishing/scam attempt, else False."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the phishing judgement, between 0.0 and 1.0.",
    )
    reasoning: str = Field(
        description="Short explanation for why the email is or is not phishing."
    )


def llm_detect_phishing_for_email(
    msg: EmailMessage,
    *,
    provider: str,
    model_name: str,
) -> Tuple[bool, dict[str, Any]]:
    """
    Detect whether an email is likely to be a phishing attempt.
    """
    chain = get_model(provider, model_name, PhishingDetectionSchema)
    email_context = build_email_context(msg)

    prompt = PHISHING_DETECTION_PROMPT.format(
        email_context=email_context,
    )

    result, llm_call_info = chain(prompt)
    return result.is_phishing, llm_call_info
