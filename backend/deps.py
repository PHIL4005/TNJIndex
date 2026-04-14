from __future__ import annotations

import sqlite3
from collections.abc import Generator

from pipelines.sqlite_vec import ensure_item_embeddings, ensure_item_image_embeddings
from scrapers.db import get_conn


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Open DB (``DATABASE_PATH`` via ``scrapers.db``), load sqlite-vec for semantic search."""
    conn = get_conn()
    ensure_item_embeddings(conn)
    ensure_item_image_embeddings(conn)
    try:
        yield conn
    finally:
        conn.close()
