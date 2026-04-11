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


def pick_image_path(thumbnail_path: str | None, image_path: str) -> Path | None:
    """Prefer thumbnail when present on disk; else original."""
    t = resolve_media(thumbnail_path)
    if t is not None and t.is_file():
        return t
    return resolve_media(image_path)
