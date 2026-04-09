"""
Database connection and schema initialization for TNJIndex.

Usage:
    uv run python scrapers/db.py          # initialize DB and print schema
    from scrapers.db import get_conn      # use in other modules
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "db" / "tnjindex.db"

CREATE_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    title             TEXT    NOT NULL DEFAULT '',
    image_path        TEXT    NOT NULL,
    thumbnail_path    TEXT,
    tags              TEXT    NOT NULL DEFAULT '[]',
    description       TEXT,
    source_note       TEXT,
    annotation_status TEXT    NOT NULL DEFAULT 'raw'
                              CHECK(annotation_status IN ('raw', 'annotated')),
    phash             TEXT,
    created_at        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
"""


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(CREATE_ITEMS_TABLE)
    print(f"[OK] DB initialized: {DB_PATH}")


# ---------- CRUD helpers ----------

def insert_item(
    conn: sqlite3.Connection,
    image_path: str,
    thumbnail_path: Optional[str] = None,
    source_note: Optional[str] = None,
    phash: Optional[str] = None,
) -> int:
    """Insert a raw item and return its id."""
    cursor = conn.execute(
        """
        INSERT INTO items (image_path, thumbnail_path, source_note, phash)
        VALUES (?, ?, ?, ?)
        """,
        (image_path, thumbnail_path, source_note, phash),
    )
    conn.commit()
    return cursor.lastrowid


def get_all_phashes(conn: sqlite3.Connection) -> list[str]:
    """Return all stored phash values (non-null) for duplicate detection."""
    rows = conn.execute("SELECT phash FROM items WHERE phash IS NOT NULL").fetchall()
    return [row["phash"] for row in rows]


def update_annotation(
    conn: sqlite3.Connection,
    item_id: int,
    title: str,
    tags: list[str],
    description: str,
) -> None:
    conn.execute(
        """
        UPDATE items
        SET title = ?, tags = ?, description = ?, annotation_status = 'annotated'
        WHERE id = ?
        """,
        (title, json.dumps(tags, ensure_ascii=False), description, item_id),
    )
    conn.commit()


if __name__ == "__main__":
    init_db()
    with get_conn() as conn:
        schema = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='items'"
        ).fetchone()
        print("\n--- items schema ---")
        print(schema["sql"])
