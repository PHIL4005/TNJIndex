"""
Minimal sqlite-vec smoke test: insert a few rows and run a KNN-style query.

Run twice in separate processes to verify persistence (M1 acceptance).

  uv run python -m pipelines.vec_smoke
"""

from __future__ import annotations

import math
import sys

from sqlite_vec import serialize_float32

from pipelines.constants import EMBEDDING_DIM, REPO_ROOT
from pipelines.sqlite_vec import ensure_item_embeddings
from scrapers.db import get_conn


def _dummy_embedding(seed: int, dim: int = EMBEDDING_DIM) -> list[float]:
    """Deterministic unit-ish vector for smoke tests only."""
    out: list[float] = []
    for i in range(dim):
        out.append(math.sin(float(seed * 17 + i + 1)) * 0.1)
    return out


def main() -> int:
    conn = get_conn()
    ensure_item_embeddings(conn)

    rows = conn.execute(
        "SELECT id FROM items ORDER BY id LIMIT 3"
    ).fetchall()
    if not rows:
        print("[vec_smoke] no items in DB; skip vector insert", file=sys.stderr)
        conn.close()
        return 0

    ids = [int(r["id"]) for r in rows]
    conn.executemany(
        "DELETE FROM item_embeddings WHERE item_id = ?",
        [(i,) for i in ids],
    )
    conn.commit()

    for item_id in ids:
        vec = _dummy_embedding(item_id)
        blob = serialize_float32(vec)
        conn.execute(
            "INSERT INTO item_embeddings(embedding, item_id) VALUES (?, ?)",
            (blob, item_id),
        )
    conn.commit()

    query = serialize_float32(_dummy_embedding(ids[0]))
    knn = conn.execute(
        """
        SELECT item_id, distance
        FROM item_embeddings
        WHERE embedding MATCH ?
        ORDER BY distance
        LIMIT 5
        """,
        (query,),
    ).fetchall()
    conn.close()

    print("[vec_smoke] item_ids touched:", ids)
    print("[vec_smoke] MATCH results:", [(r["item_id"], r["distance"]) for r in knn])
    if not knn:
        print("[vec_smoke] ERROR: empty MATCH result", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
