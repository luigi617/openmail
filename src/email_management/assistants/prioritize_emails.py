from typing import Any, Dict, List, Sequence, Tuple
from pydantic import BaseModel, Field

from email_management.llm import get_model
from email_management.models import EmailMessage
from email_management.utils import build_email_context


PRIORITIZE_EMAILS_PROMPT = """
You are an assistant that assigns a priority score to each email.

Consider:
- Urgency and explicit deadlines.
- Importance of the sender (e.g., manager, key client vs. newsletter).
- Clear requests for action or decision.
- Relevance to ongoing work or commitments.

Instructions:
- Each email is identified by an Email ID.
- For each email, you must output:
  - id: the Email ID (copied exactly as given)
  - score: a numeric priority score between 0.0 and 1.0
    - 1.0 = extremely urgent and important
    - 0.0 = trivial / ignorable
- Base the score only on the email content and metadata provided.
- Do not omit any email; produce one item for every Email ID.

Emails:
{email_blocks}
"""


class EmailPriorityItem(BaseModel):
    id: str = Field(
        description="Opaque ID that identifies one email exactly as given in the prompt."
    )
    score: float = Field(
        ge=0.0,
        le=1.0,
        description="Priority score between 0.0 (trivial) and 1.0 (critical).",
    )


class EmailPrioritySchema(BaseModel):
    items: List[EmailPriorityItem] = Field(
        description=(
            "List of priority results. Each item contains an email id and a score. "
            "There must be one item per email."
        )
    )


def llm_prioritize_emails(
    messages: Sequence[EmailMessage],
    *,
    model_path: str,
) -> Tuple[List[float], Dict[str, Any]]:
    """
    Assign a priority score to multiple emails at once.
    """
    if not messages:
        return [], {}

    # Create stable IDs for each message: e1, e2, ...
    id_list = [f"e{i + 1}" for i in range(len(messages))]
    id_to_index = {id_: i for i, id_ in enumerate(id_list)}

    # Build prompt email blocks
    email_blocks = "\n\n".join(
        f"Email ID: {email_id}\n{build_email_context(msg)}"
        for email_id, msg in zip(id_list, messages)
    )

    prompt = PRIORITIZE_EMAILS_PROMPT.format(
        email_blocks=email_blocks,
    )

    chain = get_model(model_path, EmailPrioritySchema)
    result, llm_call_info = chain(prompt)

    # Prepare an output list aligned to messages order
    scores: List[float] = [0.0] * len(messages)

    # Fill scores by placing them at the appropriate index
    for item in result.items:
        idx = id_to_index.get(item.id)
        if idx is not None:
            scores[idx] = item.score

    return scores, llm_call_info