"""Jina CLIP v2 image embeddings (HTTP) for sqlite-vec `item_image_embeddings` row width."""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
import sqlite3
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from PIL import Image

from pipelines.constants import (
    CLIP_IMAGE_EMBEDDING_DIM,
    DEFAULT_JINA_CLIP_MODEL,
    JINA_EMBEDDINGS_URL,
    REPO_ROOT,
)
from pipelines.paths import is_http_url, pick_image_for_vision
from pipelines.sqlite_vec import ensure_item_image_embeddings, replace_item_image_embedding

_DOTENV_DONE = False


def _load_dotenv_once() -> None:
    global _DOTENV_DONE
    if _DOTENV_DONE:
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env", override=False)
    except ImportError:
        pass
    _DOTENV_DONE = True


def _require_jina_key() -> str:
    _load_dotenv_once()
    key = (os.environ.get("JINA_API_KEY") or "").strip()
    if not key:
        raise RuntimeError(
            "缺少环境变量 JINA_API_KEY。请在 .env 中设置 JINA_API_KEY=jina_... 或 export JINA_API_KEY=..."
        )
    return key


def _jina_model() -> str:
    return (os.environ.get("TNJ_JINA_CLIP_MODEL") or DEFAULT_JINA_CLIP_MODEL).strip()


def _jina_url() -> str:
    """Full ``.../v1/embeddings`` URL; override with ``JINA_EMBEDDINGS_URL``."""
    return (os.environ.get("JINA_EMBEDDINGS_URL") or JINA_EMBEDDINGS_URL).strip().rstrip("/")


def _parse_embedding_response(data: dict[str, Any]) -> list[float]:
    rows = data.get("data")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("jina_embed_empty_data")
    first = rows[0]
    if not isinstance(first, dict):
        raise RuntimeError("jina_embed_bad_data_row")
    emb = first.get("embedding")
    if not isinstance(emb, list):
        raise RuntimeError("jina_embed_missing_embedding")
    vec = [float(x) for x in emb]
    if len(vec) != CLIP_IMAGE_EMBEDDING_DIM:
        raise RuntimeError(
            f"jina_embedding_dim_mismatch: expected {CLIP_IMAGE_EMBEDDING_DIM}, got {len(vec)}"
        )
    return vec


def _post_jina(*, input_payload: list[dict[str, Any] | str]) -> list[float]:
    key = _require_jina_key()
    url = _jina_url()
    body: dict[str, Any] = {
        "model": _jina_model(),
        "input": input_payload,
        "dimensions": CLIP_IMAGE_EMBEDDING_DIM,
        "normalized": True,
        "embedding_type": "float",
    }
    resp = requests.post(
        url,
        json=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        timeout=120,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"jina_embed_http_{resp.status_code}: {resp.text[:500]}")
    return _parse_embedding_response(resp.json())


def _bytes_to_data_uri(data: bytes, *, mime: str | None) -> str:
    mt = (mime or "image/jpeg").strip() or "image/jpeg"
    b64 = base64.standard_b64encode(data).decode("ascii")
    return f"data:{mt};base64,{b64}"


def _mime_from_pillow(data: bytes) -> str:
    with Image.open(BytesIO(data)) as im:
        fmt = (im.format or "JPEG").upper()
    mapping = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "GIF": "image/gif"}
    return mapping.get(fmt, "image/jpeg")


def encode_image_bytes(data: bytes, *, mime: str | None = None) -> list[float]:
    """
    Embed raw image bytes (e.g. uploaded file). ``mime`` optional; inferred via Pillow when omitted.
    """
    if len(data) > 5 * 1024 * 1024:
        raise ValueError("image_too_large: max 5MB for Jina Embedding API")
    mt = mime or _mime_from_pillow(data)
    # Jina `/v1/embeddings` expects multimodal items as `{"image": url_or_base64}` (not `url`/`bytes`).
    return _post_jina(input_payload=[{"image": _bytes_to_data_uri(data, mime=mt)}])


def encode_image_url(url: str) -> list[float]:
    """Embed an image reachable at a public HTTP(S) URL (e.g. OSS)."""
    u = (url or "").strip()
    if not is_http_url(u):
        raise ValueError("encode_image_url expects http(s) URL")
    return _post_jina(input_payload=[{"image": u}])


def encode_image_path(path: str | Path) -> list[float]:
    """
    Embed from a local filesystem path or an ``https://`` URL string.
    Local path: read bytes and send as base64. URL: delegates to ``encode_image_url``.
    """
    s = str(path).strip()
    if is_http_url(s):
        return encode_image_url(s)
    p = Path(s)
    if not p.is_file():
        raise FileNotFoundError(f"image_not_found: {p}")
    data = p.read_bytes()
    mime, _ = mimetypes.guess_type(p.name)
    return encode_image_bytes(data, mime=mime)


def encode_image_ref(ref: str | Path) -> list[float]:
    """Dispatch: URL string → URL API; else local path."""
    if isinstance(ref, str) and is_http_url(ref.strip()):
        return encode_image_url(ref.strip())
    return encode_image_path(ref)


def index_item_image(
    conn: sqlite3.Connection,
    *,
    item_id: int,
    thumbnail_path: str | None,
    image_path: str,
) -> bool:
    """
    Encode item image (thumbnail / original / OSS URL) and upsert into ``item_image_embeddings``.

    Returns True on success. Returns False and logs nothing on missing ref or missing API key
    (ingest remains usable without Jina). Raises on API errors when key is present.
    """
    log = logging.getLogger(__name__)
    _load_dotenv_once()
    if not (os.environ.get("JINA_API_KEY") or "").strip():
        log.warning("[clip] JINA_API_KEY unset, skip image index for item_id=%s", item_id)
        return False

    ref = pick_image_for_vision(thumbnail_path, image_path)
    if ref is None:
        log.warning("[clip] no image ref for item_id=%s, skip", item_id)
        return False

    ensure_item_image_embeddings(conn)
    try:
        if isinstance(ref, Path):
            vec = encode_image_path(ref)
        else:
            vec = encode_image_url(str(ref))
        replace_item_image_embedding(conn, item_id, vec)
        conn.commit()
    except Exception as e:  # noqa: BLE001
        log.warning("[clip] failed item_id=%s: %s", item_id, e)
        return False
    return True
