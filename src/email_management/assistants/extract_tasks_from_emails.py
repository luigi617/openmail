from typing import Any, Dict, List, Sequence, Tuple, Optional
from pydantic import BaseModel, Field

from email_management.llm import get_model
from email_management.models import EmailMessage
from email_management.utils import build_email_context


TASK_EXTRACTION_PROMPT = """
You are an assistant that extracts actionable tasks from emails.

Instructions:
- Read the email context carefully.
- Identify concrete action items (things that someone should do).
- Include tasks even if they are only implied but reasonably clear.
- Each task should be specific enough that someone can act on it.
- If due dates or deadlines are mentioned, capture them.
- If a responsible person is clear, capture them as the assignee.
- If there are no tasks, return an empty list.

Email context:
{email_context}
"""

class MetadataItem(BaseModel):
    key: str = Field(description="Metadata key.")
    value: str = Field(description="Metadata value.")

class TaskSchema(BaseModel):
    """
    Generic task structure that can be reused across domains.
    """
    id: Optional[str] = Field(
        default=None,
        description="A stable identifier if available; otherwise null."
    )
    title: str = Field(
        description="Short, human-readable label for the task."
    )
    description: str = Field(
        description="Longer description with relevant context for the task."
    )
    due_date: Optional[str] = Field(
        default=None,
        description="Due date or deadline in ISO 8601 format if specified; otherwise null."
    )
    priority: Optional[str] = Field(
        default=None,
        description='Priority such as "low", "medium", or "high", if inferable.'
    )
    status: Optional[str] = Field(
        default=None,
        description='Status such as "todo", "in_progress", or "done"; usually "todo".'
    )
    assignee: Optional[str] = Field(
        default=None,
        description="Person responsible for the task if known."
    )
    tags: List[str] = Field(
        default_factory=list,
        description="List of keywords or labels for the task."
    )
    source_system: str = Field(
        description='Source system for the task, e.g. "email".'
    )
    source_id: Optional[str] = Field(
        default=None,
        description="Identifier of the source record (e.g. message ID) if available."
    )
    source_link: Optional[str] = Field(
        default=None,
        description="Deep link/URL to the source record if available."
    )
    metadata: List[MetadataItem] = Field(
        default_factory=list,
        description="Additional domain-specific metadata as key-value pairs."
    )


class TaskExtractionSchema(BaseModel):
    tasks: List[TaskSchema] = Field(
        description="List of tasks extracted from the email context."
    )


def llm_extract_tasks_from_emails(
    messages: Sequence[EmailMessage],
    *,
    model_path: str,
) -> Tuple[List[Dict[str, Any]], dict[str, Any]]:
    """
    Extract tasks from one or more emails using a generic task structure.
    """
    # Combine contexts from all messages.
    parts: List[str] = []
    for idx, msg in enumerate(messages, start=1):
        ctx = build_email_context(msg)
        parts.append(f"--- Email #{idx} ---\n{ctx}\n")

    email_context = "\n".join(parts)

    chain = get_model(model_path, TaskExtractionSchema)
    result, llm_call_info = chain(
        TASK_EXTRACTION_PROMPT.format(email_context=email_context)
    )

    # Return as list of plain dicts so callers don't depend on Pydantic models.
    tasks_dicts: List[Dict[str, Any]] = [t.model_dump() for t in result.tasks]
    return tasks_dicts, llm_call_info
