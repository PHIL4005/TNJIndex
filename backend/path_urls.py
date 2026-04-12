from __future__ import annotations

from typing import Optional


def resolve_media_url(rel: Optional[str]) -> Optional[str]:
    """Map DB-relative paths to ``/media/...``; pass through http(s) URLs."""
    if not rel or not str(rel).strip():
        return None
    s = str(rel).replace("\\", "/").strip()
    lower = s.lower()
    if lower.startswith("https://") or lower.startswith("http://"):
        return s
    prefix = "data/images/"
    if s.startswith(prefix):
        return "/media/" + s[len(prefix) :].lstrip("/")
    if s.startswith("images/"):
        return "/media/" + s[len("images/") :].lstrip("/")
    return "/media/" + s.lstrip("/")
