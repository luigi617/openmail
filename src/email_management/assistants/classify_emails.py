from typing import Any, Dict, List, Sequence, Tuple
from pydantic import BaseModel, Field

from email_management.llm import get_model
from email_management.models import EmailMessage
from email_management.utils import build_email_context


CLASSIFY_EMAILS_PROMPT = """
You are an assistant that classifies emails into one of a small set of classes.

Instructions:
- You will be given multiple emails, each with an Email ID.
- For each email, choose exactly ONE class from the allowed list.
- For the output, return a list of objects, each with:
  - id: the Email ID (copied exactly as given)
  - label: the chosen class
- Do not invent new class names; only use the provided classes.

Allowed classes:
{classes}

Emails:
{email_blocks}
"""


class EmailClassificationItem(BaseModel):
    id: str = Field(description="Opaque ID that identifies one email.")
    label: str = Field(description="Chosen class label for this email.")

class EmailClassificationSchema(BaseModel):
    items: List[EmailClassificationItem] = Field(
        description=(
            "List of classification results. Each item contains the email id "
            "and the chosen class label."
        )
    )


def llm_classify_emails(
    messages: Sequence[EmailMessage],
    *,
    classes: Sequence[str],
    model_path: str,
) -> Tuple[Dict[EmailMessage, str], Dict[str, Any]]:
    if not messages:
        return [], {}

    chain = get_model(model_path, EmailClassificationSchema)

    # synthetic IDs: e1, e2, ...
    id_list = [f"e{i + 1}" for i in range(len(messages))]
    id_to_index = {id_: i for i, id_ in enumerate(id_list)}

    classes_str = ", ".join(classes)

    # context blocks with IDs
    email_blocks = "\n\n".join(
        f"Email ID: {email_id}\n{build_email_context(msg)}"
        for email_id, msg in zip(id_list, messages)
    )

    prompt = CLASSIFY_EMAILS_PROMPT.format(
        classes=classes_str,
        email_blocks=email_blocks,
    )

    result, llm_call_info = chain(prompt)

    # prepare output aligned to input order
    labels: List[str] = [""] * len(messages)

    for item in result.items:
        idx = id_to_index.get(item.id)
        if idx is not None:
            labels[idx] = item.label

    return labels, llm_call_info