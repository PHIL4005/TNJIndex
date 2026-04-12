from __future__ import annotations

import json
import os
import sqlite3

from fastapi import APIRouter, Depends, Query

from backend.deps import get_db
from backend.path_urls import resolve_media_url
from backend.schemas import ItemSummary, SearchResponse
from pipelines.search import search as semantic_search

router = APIRouter(tags=["search"])


def _semantic_distance_threshold_max() -> float:
    """Max sqlite-vec distance to keep; drop rows with distance strictly greater than this."""
    raw = (os.environ.get("SCORE_THRESHOLD_MAX") or "1.0").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.0


def _normalize_filter_tags(tags: list[str]) -> list[str]:
    out: list[str] = []
    for t in tags:
        s = (t or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def _annotated_count_sql(filter_tags: list[str]) -> tuple[str, list]:
    sql = """
        SELECT COUNT(*) AS c
        FROM items
        WHERE annotation_status = 'annotated'
    """
    params: list = []
    for tag in filter_tags:
        sql += """
          AND EXISTS (
            SELECT 1 FROM json_each(items.tags) AS j
            WHERE j.value = ?
          )
        """
        params.append(tag)
    return sql, params


def _annotated_page_sql(filter_tags: list[str]) -> tuple[str, list]:
    sql = """
        SELECT id, title, tags, thumbnail_path, image_path
        FROM items
        WHERE annotation_status = 'annotated'
    """
    params: list = []
    for tag in filter_tags:
        sql += """
          AND EXISTS (
            SELECT 1 FROM json_each(items.tags) AS j
            WHERE j.value = ?
          )
        """
        params.append(tag)
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    return sql, params


@router.get("/search", response_model=SearchResponse)
def api_search(
    q: str = "",
    tags: list[str] = Query(default=[]),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> SearchResponse:
    q_stripped = (q or "").strip()
    filter_tags = _normalize_filter_tags(tags)

    if not q_stripped:
        count_sql, count_params = _annotated_count_sql(filter_tags)
        total = int(conn.execute(count_sql, count_params).fetchone()["c"])
        page_sql, page_params = _annotated_page_sql(filter_tags)
        page_params = [*page_params, limit, offset]
        rows = conn.execute(page_sql, page_params).fetchall()
        results: list[ItemSummary] = []
        for r in rows:
            raw_tags = r["tags"]
            try:
                tags_parsed = json.loads(raw_tags or "[]")
            except json.JSONDecodeError:
                tags_parsed = []
            if not isinstance(tags_parsed, list):
                tags_parsed = []
            results.append(
                ItemSummary(
                    id=int(r["id"]),
                    title=r["title"] or "",
                    thumbnail_url=resolve_media_url(r["thumbnail_path"]),
                    tags=[str(t) for t in tags_parsed],
                    score=None,
                )
            )
        return SearchResponse(results=results, query=q_stripped, total=total)

    # Extra headroom so distance threshold + tag filter still fill the page when possible.
    fetch_k = max(1, min(limit + offset + 100, 500))
    raw_rows = semantic_search(q_stripped, k=fetch_k, conn=conn)
    dist_max = _semantic_distance_threshold_max()
    raw_rows = [
        r
        for r in raw_rows
        if r.get("score") is None or float(r["score"]) <= dist_max
    ]

    def _row_has_filter_tags(r: dict) -> bool:
        if not filter_tags:
            return True
        tlist = r.get("tags") or []
        if not isinstance(tlist, list):
            return False
        norm = {str(x) for x in tlist}
        return all(t in norm for t in filter_tags)

    filtered = [r for r in raw_rows if _row_has_filter_tags(r)]

    total = len(filtered)
    page_rows = filtered[offset : offset + limit]
    results = [
        ItemSummary(
            id=int(r["id"]),
            title=r.get("title") or "",
            thumbnail_url=resolve_media_url(r.get("thumbnail_path")),
            tags=[str(t) for t in (r.get("tags") or [])],
            score=float(r["score"]) if r.get("score") is not None else None,
        )
        for r in page_rows
    ]
    return SearchResponse(results=results, query=q_stripped, total=total)
