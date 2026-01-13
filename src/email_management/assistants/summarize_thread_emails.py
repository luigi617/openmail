from typing import Any, Tuple, List, Sequence
from pydantic import BaseModel, Field

from email_management.llm import get_model
from email_management.models import EmailMessage
from email_management.utils import build_email_context


THREAD_SUMMARY_PROMPT = """
You are an assistant that summarizes email conversation threads.

Instructions:
- Read the entire thread carefully.
- Provide a concise summary (5-10 sentences).
- Focus on:
  - Overall context and purpose of the thread.
  - Key decisions that have been made.
  - Open questions that still need answers.
  - Action items and who is responsible for them (if specified).
- Write in clear, professional language.
- Do not include greetings or sign-offs.

Email thread (oldest to newest):
{thread_context}
"""


class ThreadSummarySchema(BaseModel):
    summary: str = Field(
        description="Concise summary of the email thread, including context, decisions, open questions, and action items."
    )


def llm_summarize_thread_emails(
    messages: Sequence[EmailMessage],
    *,
    model_path: str,
) -> Tuple[str, dict[str, Any]]:
    """
    Summarize a sequence of emails representing a thread.
    """
    # Build a combined context from all messages in chronological order.
    parts: List[str] = []
    for idx, msg in enumerate(messages, start=1):
        ctx = build_email_context(msg)
        parts.append(f"--- Email #{idx} ---\n{ctx}\n")

    thread_context = "\n".join(parts)

    chain = get_model(model_path, ThreadSummarySchema)
    result, llm_call_info = chain(
        THREAD_SUMMARY_PROMPT.format(thread_context=thread_context)
    )
    return result.summary, llm_call_info
