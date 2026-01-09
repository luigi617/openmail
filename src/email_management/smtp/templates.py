from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping, Optional

@dataclass(frozen=True)
class RenderedTemplate:
    subject: str
    text: Optional[str] = None
    html: Optional[str] = None

def render_template(name: str, context: Mapping[str, object]) -> RenderedTemplate:
    # Backbone placeholder. Later: Jinja2 file loader.
    raise NotImplementedError("Template rendering not implemented yet")
