from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from backend.deps import get_db
from backend.schemas import TagCount

router = APIRouter(tags=["tags"])


@router.get("/tags", response_model=list[TagCount])
def list_tags(conn: sqlite3.Connection = Depends(get_db)) -> list[TagCount]:
    rows = conn.execute(
        """
        SELECT value AS name, COUNT(*) AS count
        FROM items, json_each(items.tags)
        WHERE annotation_status = 'annotated'
        GROUP BY value
        ORDER BY count DESC
        """
    ).fetchall()
    return [TagCount(name=str(r["name"]), count=int(r["count"])) for r in rows]
