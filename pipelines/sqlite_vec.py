"""Load sqlite-vec and ensure `item_embeddings` virtual table exists."""

from __future__ import annotations

import sqlite3

import sqlite_vec

from pipelines.constants import EMBEDDING_DIM

_ITEM_EMBEDDINGS_DDL = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS item_embeddings USING vec0(
  embedding float[{EMBEDDING_DIM}],
  +item_id INTEGER
);
"""


def enable_sqlite_vec(conn: sqlite3.Connection) -> None:
    """Load sqlite-vec into an open connection (call once per connection)."""
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


def ensure_item_embeddings(conn: sqlite3.Connection) -> None:
    """
    Create `item_embeddings` vec0 table if missing.
    `item_id` matches `items.id`; one row per indexed item (M2+).
    """
    enable_sqlite_vec(conn)
    conn.executescript(_ITEM_EMBEDDINGS_DDL)
    conn.commit()
