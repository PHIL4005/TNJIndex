from __future__ import annotations

import json
import os
import sqlite3

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from backend.deps import get_db
from backend.path_urls import resolve_media_url
from backend.schemas import ItemSummary, SearchResponse
from pipelines.search import search as semantic_search, search_by_image_bytes

router = APIRouter(tags=["search"])

# 列表可返回条数上限（防刷图/滥用）；纯浏览与「有筛选/搜索」区分
_MAX_BROWSE_LIST_ITEMS = 128
_MAX_SEARCH_LIST_ITEMS = 32


def _max_list_items(q_stripped: str, filter_tags: list[str]) -> int:
    """无 query、无标签：浏览全库列表；否则为搜索/标签筛选，上限更严。"""
    if not q_stripped and not filter_tags:
        return _MAX_BROWSE_LIST_ITEMS
    return _MAX_SEARCH_LIST_ITEMS


def _semantic_distance_threshold_max() -> float:
    """Max sqlite-vec distance to keep; drop rows with distance strictly greater than this."""
    raw = (os.environ.get("SCORE_THRESHOLD_MAX") or "1.0").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.0


_ALLOWED_IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_MAX_IMAGE_UPLOAD_BYTES = 5 * 1024 * 1024


def _normalize_upload_content_type(raw: str | None) -> str:
    if not raw:
        return ""
    return raw.split(";", 1)[0].strip().lower()


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


def _annotated_browse_shuffle_sql(shuffle_seed: int) -> tuple[str, list]:
    """纯浏览（无标签）：与 shuffle_seed 绑定的确定性顺序，分页稳定。shuffle_seed=0 时不应调用本函数。"""
    sql = """
        SELECT id, title, tags, thumbnail_path, image_path
        FROM items
        WHERE annotation_status = 'annotated'
        ORDER BY ((id * 2654435761 + ?) & 4294967295) ASC
        LIMIT ? OFFSET ?
    """
    return sql, [shuffle_seed]


@router.get("/search", response_model=SearchResponse)
def api_search(
    q: str = "",
    tags: list[str] = Query(default=[]),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    shuffle_seed: int = Query(
        0,
        ge=0,
        le=2147483647,
        description="纯浏览专用：非 0 时用与 seed 绑定的确定性顺序；0 表示 id DESC",
    ),
    conn: sqlite3.Connection = Depends(get_db),
) -> SearchResponse:
    q_stripped = (q or "").strip()
    filter_tags = _normalize_filter_tags(tags)
    cap = _max_list_items(q_stripped, filter_tags)

    if not q_stripped:
        count_sql, count_params = _annotated_count_sql(filter_tags)
        total_db = int(conn.execute(count_sql, count_params).fetchone()["c"])
        total = min(total_db, cap)
        if offset >= cap:
            return SearchResponse(results=[], query=q_stripped, total=total)
        limit_eff = min(limit, cap - offset)
        if not filter_tags and shuffle_seed != 0:
            page_sql, seed_params = _annotated_browse_shuffle_sql(shuffle_seed)
            page_params = [*seed_params, limit_eff, offset]
        else:
            page_sql, page_params = _annotated_page_sql(filter_tags)
            page_params = [*page_params, limit_eff, offset]
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
    filtered = filtered[:cap]

    total = len(filtered)
    if offset >= total:
        return SearchResponse(results=[], query=q_stripped, total=total)
    limit_eff = min(limit, total - offset)
    page_rows = filtered[offset : offset + limit_eff]
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


@router.post("/search/image", response_model=SearchResponse)
async def api_search_image(
    file: UploadFile = File(...),
    limit: int = Query(12, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> SearchResponse:
    ct = _normalize_upload_content_type(file.content_type)
    if ct not in _ALLOWED_IMAGE_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail="仅支持 JPEG、PNG、WebP 图片",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="空文件")
    if len(data) > _MAX_IMAGE_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="图片大小不能超过 5MB")

    dist_max = _semantic_distance_threshold_max()
    fetch_k = max(1, min(limit + offset + 100, 500))
    try:
        raw_rows = search_by_image_bytes(data, k=fetch_k, conn=conn, mime=ct)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    raw_rows = [
        r
        for r in raw_rows
        if r.get("score") is None or float(r["score"]) <= dist_max
    ]
    cap = _MAX_SEARCH_LIST_ITEMS
    raw_rows = raw_rows[:cap]
    total = len(raw_rows)
    if offset >= total:
        return SearchResponse(results=[], query="", total=total)
    limit_eff = min(limit, total - offset)
    page_rows = raw_rows[offset : offset + limit_eff]
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
    return SearchResponse(results=results, query="", total=total)
