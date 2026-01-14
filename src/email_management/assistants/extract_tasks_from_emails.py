from __future__ import annotations
from typing import Any, List, Sequence, Tuple, Optional
from pydantic import BaseModel, Field
from email_management.llm import get_model
from email_management.models import EmailMessage
from email_management.utils import build_email_context
from email_management.models import Task


TASK_EXTRACTION_PROMPT = """
You extract only important actionable tasks from one or more emails.

Rules:
- Be selective. Prefer missing minor tasks over adding noise.
- Return at most 3 tasks per email.
- Ignore emails without clearly actionable requests.
- If no important tasks exist, return an empty list.
- Do NOT invent tasks.

Important tasks:
- Explicit or implied requests for the recipient to act.
- Deliverables, follow-ups, decisions, or deadlines.
- Items with urgency or due dates.

Exclude:
- Promotions, marketing, newsletters.
- FYI/announcements with no request.
- Low-importance suggestions or optional ideas.
- Automated notifications with no follow-up needed.

Task fields:
- Capture due dates and assignees if stated or clearly implied.
- Set priority only if urgency is explicit.
- Status is usually "todo".

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
    provider: str,
    model_name: str,
) -> Tuple[List[Task], dict[str, Any]]:
    """
    Extract tasks from one or more emails using a generic task structure.
    """
    parts: List[str] = []
    for idx, msg in enumerate(messages, start=1):
        ctx = build_email_context(msg)
        parts.append(f"--- Email #{idx} ---\n{ctx}\n")

    email_context = "\n".join(parts)

    chain = get_model(provider, model_name, TaskExtractionSchema)
    result, llm_call_info = chain(
        TASK_EXTRACTION_PROMPT.format(email_context=email_context)
    )

    tasks: List[Task] = []
    for t in result.tasks:
        tasks.append(
            Task(
                id=t.id,
                title=t.title,
                description=t.description,
                due_date=t.due_date,
                priority=t.priority,
                status=t.status,
                assignee=t.assignee,
                tags=t.tags,
                source_system=t.source_system,
                source_id=t.source_id,
                source_link=t.source_link,
                metadata={item.key: item.value for item in t.metadata}
            )
        )
    return tasks, llm_call_info
