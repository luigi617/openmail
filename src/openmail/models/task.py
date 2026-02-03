
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Task:
    """
    Common task structure that can be used in different domains
    """
    id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    assignee: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    source_system: Optional[str] = None
    source_id: Optional[str] = None
    source_link: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)