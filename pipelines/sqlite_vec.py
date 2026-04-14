"""Load sqlite-vec and ensure `item_embeddings` virtual table exists."""

from __future__ import annotations

import sqlite3

import sqlite_vec

from pipelines.constants import CLIP_IMAGE_EMBEDDING_DIM, EMBEDDING_DIM

_ITEM_EMBEDDINGS_DDL = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS item_embeddings USING vec0(
  embedding float[{EMBEDDING_DIM}],
  +item_id INTEGER
);
"""

_ITEM_IMAGE_EMBEDDINGS_DDL = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS item_image_embeddings USING vec0(
  image_embedding float[{CLIP_IMAGE_EMBEDDING_DIM}],
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


def ensure_item_image_embeddings(conn: sqlite3.Connection) -> None:
    """
    Create `item_image_embeddings` vec0 table if missing (Jina CLIP v2, 1024-dim).
    `item_id` matches `items.id`; one row per image-indexed item (S2).
    """
    enable_sqlite_vec(conn)
    conn.executescript(_ITEM_IMAGE_EMBEDDINGS_DDL)
    conn.commit()


def replace_item_image_embedding(conn: sqlite3.Connection, item_id: int, vec: list[float]) -> None:
    """Replace CLIP image vector for ``item_id`` (caller should ``commit`` as needed)."""
    from sqlite_vec import serialize_float32

    if len(vec) != CLIP_IMAGE_EMBEDDING_DIM:
        raise ValueError(
            f"image_embedding_dim_mismatch: expected {CLIP_IMAGE_EMBEDDING_DIM}, got {len(vec)}"
        )
    blob = serialize_float32(vec)
    conn.execute("DELETE FROM item_image_embeddings WHERE item_id = ?", (item_id,))
    conn.execute(
        "INSERT INTO item_image_embeddings(image_embedding, item_id) VALUES (?, ?)",
        (blob, item_id),
    )
