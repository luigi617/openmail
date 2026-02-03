from __future__ import annotations

import re
from typing import List

from openmail.models import UnsubscribeMethod

_LIST_UNSUB_RE = re.compile(r"<\s*([^>]+?)\s*>")


def parse_list_unsubscribe(value: str) -> List[UnsubscribeMethod]:
    """
    Parses:
      <mailto:unsubscribe@x.com>, <https://x.com/unsub>
    """
    if not value:
        return []

    methods: List[UnsubscribeMethod] = []

    for item in _LIST_UNSUB_RE.findall(value):
        item = item.strip()

        if item.lower().startswith("mailto:"):
            addr = item[len("mailto:"):].split("?", 1)[0].strip()
            if addr:
                methods.append(UnsubscribeMethod("mailto", addr))

        elif item.lower().startswith(("http://", "https://")):
            methods.append(UnsubscribeMethod("http", item))

    return methods
