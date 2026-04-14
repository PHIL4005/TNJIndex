"""Semantic search over item_embeddings + items (single implementation for CLI / Web)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from sqlite_vec import serialize_float32

from pipelines.clip_embed import encode_image_bytes
from pipelines.embed_client import Provider, embed_text
from pipelines.sqlite_vec import ensure_item_embeddings, ensure_item_image_embeddings
from scrapers.db import get_conn


def search(
    query: str,
    k: int = 10,
    conn: sqlite3.Connection | None = None,
    *,
    provider: Provider | None = None,
) -> list[dict[str, Any]]:
    """
    Embed ``query``, run sqlite-vec KNN on ``item_embeddings``, then load ``items`` rows.

    Returns list of dicts: id, score (distance), title, tags (list[str]), description,
    thumbnail_path, image_path.

    If ``conn`` is omitted, opens/closes a new connection (with sqlite-vec loaded).
    """
    q = (query or "").strip()
    if not q:
        return []

    close_conn = False
    if conn is None:
        conn = get_conn()
        close_conn = True

    try:
        ensure_item_embeddings(conn)
        qvec = embed_text(q, provider=provider)
        blob = serialize_float32(qvec)
        k_safe = max(1, min(int(k), 500))
        # KNN 仅取 id+distance；再 JOIN items 会在部分 sqlite-vec 版本触发 auxiliary 约束错误
        knn = conn.execute(
            """
            SELECT item_id, distance
            FROM item_embeddings
            WHERE embedding MATCH ?
              AND k = ?
            """,
            (blob, k_safe),
        ).fetchall()
        if not knn:
            return []

        order_ids = [int(r["item_id"]) for r in knn]
        dist_map = {
            int(r["item_id"]): float(r["distance"]) if r["distance"] is not None else 0.0 for r in knn
        }
        placeholders = ",".join("?" * len(order_ids))
        rows = conn.execute(
            f"""
            SELECT id, title, tags, description, thumbnail_path, image_path
            FROM items
            WHERE id IN ({placeholders})
            """,
            order_ids,
        ).fetchall()
        row_by_id = {int(r["id"]): r for r in rows}

        out: list[dict[str, Any]] = []
        for item_id in order_ids:
            r = row_by_id.get(item_id)
            if r is None:
                continue
            raw_tags = r["tags"]
            try:
                tags_parsed = json.loads(raw_tags or "[]")
            except json.JSONDecodeError:
                tags_parsed = []
            if not isinstance(tags_parsed, list):
                tags_parsed = []
            score = dist_map.get(item_id, 0.0)
            out.append(
                {
                    "id": int(r["id"]),
                    "score": score,
                    "title": r["title"] or "",
                    "tags": [str(t) for t in tags_parsed],
                    "description": r["description"] or "",
                    "thumbnail_path": r["thumbnail_path"],
                    "image_path": r["image_path"] or "",
                }
            )
        return out
    finally:
        if close_conn:
            conn.close()


def search_by_image_bytes(
    data: bytes,
    k: int = 10,
    conn: sqlite3.Connection | None = None,
    *,
    mime: str | None = None,
) -> list[dict[str, Any]]:
    """
    Embed image bytes (CLIP), KNN on ``item_image_embeddings``, then load ``items`` rows.

    Same shape as ``search()`` rows: id, score, title, tags, description, thumbnail_path,
    image_path. Only items with ``annotation_status = 'annotated'`` are returned.
    """
    close_conn = False
    if conn is None:
        conn = get_conn()
        close_conn = True

    try:
        ensure_item_image_embeddings(conn)
        qvec = encode_image_bytes(data, mime=mime)
        blob = serialize_float32(qvec)
        k_safe = max(1, min(int(k), 500))
        knn = conn.execute(
            """
            SELECT item_id, distance
            FROM item_image_embeddings
            WHERE image_embedding MATCH ?
              AND k = ?
            """,
            (blob, k_safe),
        ).fetchall()
        if not knn:
            return []

        order_ids = [int(r["item_id"]) for r in knn]
        dist_map = {
            int(r["item_id"]): float(r["distance"]) if r["distance"] is not None else 0.0 for r in knn
        }
        placeholders = ",".join("?" * len(order_ids))
        rows = conn.execute(
            f"""
            SELECT id, title, tags, description, thumbnail_path, image_path
            FROM items
            WHERE id IN ({placeholders})
              AND annotation_status = 'annotated'
            """,
            order_ids,
        ).fetchall()
        row_by_id = {int(r["id"]): r for r in rows}

        out: list[dict[str, Any]] = []
        for item_id in order_ids:
            r = row_by_id.get(item_id)
            if r is None:
                continue
            raw_tags = r["tags"]
            try:
                tags_parsed = json.loads(raw_tags or "[]")
            except json.JSONDecodeError:
                tags_parsed = []
            if not isinstance(tags_parsed, list):
                tags_parsed = []
            score = dist_map.get(item_id, 0.0)
            out.append(
                {
                    "id": int(r["id"]),
                    "score": score,
                    "title": r["title"] or "",
                    "tags": [str(t) for t in tags_parsed],
                    "description": r["description"] or "",
                    "thumbnail_path": r["thumbnail_path"],
                    "image_path": r["image_path"] or "",
                }
            )
        return out
    finally:
        if close_conn:
            conn.close()
