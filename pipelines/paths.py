"""Resolve image paths relative to repository root."""

from __future__ import annotations

from pathlib import Path

from pipelines.constants import REPO_ROOT


def resolve_media(rel: str | None) -> Path | None:
    if not rel or not str(rel).strip():
        return None
    p = Path(rel)
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p


def _strip(s: str | None) -> str:
    return (s or "").strip()


def is_http_url(s: str) -> bool:
    sl = s.lower().strip()
    return sl.startswith("http://") or sl.startswith("https://")


def pick_image_for_vision(thumbnail_path: str | None, image_path: str) -> Path | str | None:
    """
    Resolve an image for Vision APIs.

    Order: local thumbnail file → local original file → thumbnail URL → original URL.

    Returns a ``Path`` only when the file exists on disk; otherwise an ``https`` URL
    string when DB stores OSS/public URLs (no download — model side fetches).
    """
    t = _strip(thumbnail_path)
    img = _strip(image_path)

    if t and not is_http_url(t):
        p = resolve_media(t)
        if p is not None and p.is_file():
            return p
    if img and not is_http_url(img):
        p = resolve_media(img)
        if p is not None and p.is_file():
            return p
    if t and is_http_url(t):
        return t
    if img and is_http_url(img):
        return img
    return None


def pick_image_path(thumbnail_path: str | None, image_path: str) -> Path | None:
    """Prefer thumbnail when present on disk; else original. HTTP(S) URLs → None."""
    ref = pick_image_for_vision(thumbnail_path, image_path)
    return ref if isinstance(ref, Path) else None
