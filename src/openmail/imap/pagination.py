from dataclasses import dataclass
from typing import List, Optional

from openmail.types import EmailRef


@dataclass
class PagedSearchResult:
    refs: List["EmailRef"]
    next_before_uid: Optional[int] = None
    prev_after_uid: Optional[int] = None
    newest_uid: Optional[int] = None
    oldest_uid: Optional[int] = None
    total: Optional[int] = None
    has_next: bool = False
    has_prev: bool = False
