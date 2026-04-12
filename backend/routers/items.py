from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.deps import get_db
from backend.path_urls import resolve_media_url
from backend.schemas import ItemDetail

router = APIRouter(tags=["items"])


@router.get("/items/{item_id}", response_model=ItemDetail)
def get_item(
    item_id: int,
    conn: sqlite3.Connection = Depends(get_db),
) -> ItemDetail:
    row = conn.execute(
        """
        SELECT id, title, tags, description, thumbnail_path, image_path
        FROM items
        WHERE id = ?
        """,
        (item_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found")
    raw_tags = row["tags"]
    try:
        tags_parsed = json.loads(raw_tags or "[]")
    except json.JSONDecodeError:
        tags_parsed = []
    if not isinstance(tags_parsed, list):
        tags_parsed = []
    return ItemDetail(
        id=int(row["id"]),
        title=row["title"] or "",
        image_url=resolve_media_url(row["image_path"]),
        thumbnail_url=resolve_media_url(row["thumbnail_path"]),
        tags=[str(t) for t in tags_parsed],
        description=row["description"],
    )
