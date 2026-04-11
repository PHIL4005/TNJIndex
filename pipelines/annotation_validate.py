"""Validate Vision JSON output against tech_design §1."""

from __future__ import annotations

import json
import re
from typing import Any

_TITLE_RE = re.compile(r"^[a-z0-9_]{1,80}$")


def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def parse_vision_json(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    """Parse model output into a dict; on failure return (None, error)."""
    text = _strip_code_fence(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return None, f"invalid_json: {e}"
    if not isinstance(data, dict):
        return None, "json_not_object"
    return data, None


def validate_annotation(data: dict[str, Any]) -> tuple[bool, str]:
    """Return (ok, reason_if_not_ok)."""
    title = data.get("title")
    if not isinstance(title, str) or not _TITLE_RE.match(title):
        return False, "title_must_be_snake_case_1_80"

    tags = data.get("tags")
    if not isinstance(tags, list) or len(tags) < 1:
        return False, "tags_must_be_nonempty_list"
    if len(tags) > 16:
        return False, "tags_too_many"
    for t in tags:
        if not isinstance(t, str) or not t.strip():
            return False, "tags_must_be_non_empty_strings"

    desc = data.get("description")
    if not isinstance(desc, str):
        return False, "description_must_be_string"
    if len(desc) > 500:
        return False, "description_too_long"

    return True, ""
