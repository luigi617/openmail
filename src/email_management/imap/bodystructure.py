from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from email_management.models import AttachmentMeta

BODYSTRUCTURE_RE = re.compile(r"BODYSTRUCTURE\s+(\(.*\))", re.IGNORECASE | re.DOTALL)


def _tokenize(s: str) -> List[str]:
    out: List[str] = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c.isspace():
            i += 1
            continue
        if c in ("(", ")"):
            out.append(c)
            i += 1
            continue
        if c == '"':
            i += 1
            buf = []
            while i < n:
                if s[i] == '"' and s[i - 1] != "\\":
                    break
                buf.append(s[i])
                i += 1
            out.append("".join(buf))
            i += 1
            continue

        j = i
        while j < n and (not s[j].isspace()) and s[j] not in ("(", ")"):
            j += 1
        out.append(s[i:j])
        i = j

    return out


def _parse_tokens(tokens: List[str], idx: int = 0) -> Tuple[Any, int]:
    if tokens[idx] != "(":
        return tokens[idx], idx + 1

    idx += 1
    lst: List[Any] = []
    while idx < len(tokens) and tokens[idx] != ")":
        tok = tokens[idx]
        if tok == "(":
            node, idx = _parse_tokens(tokens, idx)
            lst.append(node)
        else:
            lst.append(tok)
            idx += 1

    if idx >= len(tokens) or tokens[idx] != ")":
        raise ValueError("Unbalanced parentheses in BODYSTRUCTURE")

    idx += 1
    return lst, idx


def parse_bodystructure(bodystructure_str: str) -> Any:
    tokens = _tokenize(bodystructure_str)
    tree, _ = _parse_tokens(tokens, 0)
    return tree


@dataclass(frozen=True)
class TextPartRef:
    part: str
    content_type: str
    charset: Optional[str]


def _parse_param_list(x: Any) -> Dict[str, str]:
    if not isinstance(x, list):
        return {}
    out: Dict[str, str] = {}
    i = 0
    while i + 1 < len(x):
        out[str(x[i]).lower()] = str(x[i + 1])
        i += 2
    return out


def _find_disposition_filename(dispo: Any) -> Optional[str]:
    if not isinstance(dispo, list) or not dispo:
        return None
    params = _parse_param_list(dispo[1]) if len(dispo) > 1 else {}
    return params.get("filename") or params.get("name")


def _leaf_is_attachment(node: list) -> bool:
    if not isinstance(node, list) or len(node) < 7:
        return False
    params = _parse_param_list(node[2])
    dispo = node[8] if len(node) > 8 else None
    disp_filename = _find_disposition_filename(dispo)
    return bool(disp_filename or ("name" in params))


def _leaf_size(node: list) -> int:
    try:
        return int(node[6])
    except Exception:
        return 0


def _leaf_content_type(node: list) -> str:
    try:
        return f"{str(node[0]).lower()}/{str(node[1]).lower()}"
    except Exception:
        return "application/octet-stream"


def _leaf_charset(node: list) -> Optional[str]:
    params = _parse_param_list(node[2]) if len(node) > 2 else {}
    return params.get("charset")


def _leaf_filename(node: list) -> str:
    params = _parse_param_list(node[2]) if len(node) > 2 else {}
    dispo = node[8] if len(node) > 8 else None
    fn = _find_disposition_filename(dispo) or params.get("name")
    return fn or "attachment"


def extract_text_and_attachments(bodystructure: Any) -> Tuple[List[TextPartRef], List[AttachmentMeta]]:
    text_parts: List[TextPartRef] = []
    atts: List[AttachmentMeta] = []

    def walk(node: Any, prefix: str) -> None:
        if isinstance(node, list) and node:
            # Multipart: consecutive list children, followed by subtype atom(s)
            if isinstance(node[0], list):
                child_index = 1
                for child in node:
                    if not isinstance(child, list):
                        break
                    part_no = f"{prefix}.{child_index}" if prefix else str(child_index)
                    walk(child, part_no)
                    child_index += 1
                return

            # Leaf
            ctype = _leaf_content_type(node)
            if ctype in ("text/plain", "text/html"):
                text_parts.append(
                    TextPartRef(
                        part=prefix or "1",
                        content_type=ctype,
                        charset=_leaf_charset(node),
                    )
                )
                return

            if _leaf_is_attachment(node):
                atts.append(
                    AttachmentMeta(
                        idx=len(atts),
                        part=prefix or "1",
                        filename=_leaf_filename(node),
                        content_type=ctype,
                        size=_leaf_size(node),
                    )
                )
                return

    walk(bodystructure, "")
    return text_parts, atts


def pick_best_text_parts(parts: List[TextPartRef]) -> Tuple[Optional[TextPartRef], Optional[TextPartRef]]:
    plain = next((p for p in parts if p.content_type == "text/plain"), None)
    html = next((p for p in parts if p.content_type == "text/html"), None)
    return plain, html


def extract_bodystructure_from_fetch_meta(meta_str: str) -> Optional[str]:
    m = BODYSTRUCTURE_RE.search(meta_str)
    return m.group(1) if m else None
