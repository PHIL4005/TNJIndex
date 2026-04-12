"""
Database connection and schema initialization for TNJIndex.

Usage:
    uv run python scrapers/db.py          # initialize DB and print schema
    from scrapers.db import get_conn      # use in other modules
"""

import json
import os
from pathlib import Path
from typing import Optional

def get_db_path() -> Path:
    """Resolve SQLite path: ``DATABASE_PATH`` if set, else default under ``data/db/``."""
    raw = os.environ.get("DATABASE_PATH")
    if raw and str(raw).strip():
        return Path(str(raw).strip()).expanduser()
    return Path(__file__).parent.parent / "data" / "db" / "tnjindex.db"


def _sqlite3_module():
    """Prefer stdlib sqlite3 when it supports extensions; else pysqlite3 (e.g. macOS system Python)."""
    import sqlite3 as std_sqlite3

    try:
        c = std_sqlite3.connect(":memory:")
        c.enable_load_extension(True)
        c.close()
        return std_sqlite3
    except AttributeError:
        pass
    try:
        import pysqlite3.dbapi2 as pysqlite3  # type: ignore[import-not-found]

        return pysqlite3
    except ImportError as e:
        raise RuntimeError(
            "当前 Python 的 sqlite3 不支持 load_extension，且未安装 pysqlite3；"
            "无法加载 sqlite-vec。请安装 pysqlite3 或使用支持扩展的 Python 构建。"
        ) from e


sqlite3 = _sqlite3_module()

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
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(CREATE_ITEMS_TABLE)
    print(f"[OK] DB initialized: {get_db_path()}")


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


def get_all_source_notes(conn: sqlite3.Connection) -> set[str]:
    """Distinct source_note values (non-empty), for crawler resume / dedup by URL."""
    rows = conn.execute(
        "SELECT DISTINCT source_note FROM items WHERE source_note IS NOT NULL AND TRIM(source_note) != ''"
    ).fetchall()
    return {row["source_note"] for row in rows}


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
