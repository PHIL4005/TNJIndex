"""
Batch CLIP image embedding for annotated items → item_image_embeddings.

  uv run python -m pipelines.clip_embed_all --dry-run
  uv run python -m pipelines.clip_embed_all --limit 50
  uv run python -m pipelines.clip_embed_all --force

Requires JINA_API_KEY (see .env).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from pipelines.clip_embed import encode_image_path, encode_image_url
from pipelines.constants import REPO_ROOT
from pipelines.paths import pick_image_for_vision
from pipelines.sqlite_vec import ensure_item_image_embeddings, replace_item_image_embedding
from scrapers.db import get_conn


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env", override=False)
    except ImportError:
        pass


def _embed_ref(ref: Path | str) -> list[float]:
    if isinstance(ref, Path):
        return encode_image_path(ref)
    return encode_image_url(str(ref))


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Embed annotated item images into item_image_embeddings.")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max items to process (default 0 = all pending)",
    )
    parser.add_argument("--dry-run", action="store_true", help="List work only, no API/DB writes")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-embed items that already have a row in item_image_embeddings",
    )
    args = parser.parse_args(argv)

    if not args.dry_run and not (os.environ.get("JINA_API_KEY") or "").strip():
        print("[clip_embed_all] ERROR: 缺少 JINA_API_KEY", file=sys.stderr)
        return 2

    conn = get_conn()
    ensure_item_image_embeddings(conn)

    if args.force:
        sql = """
            SELECT id, image_path, thumbnail_path
            FROM items
            WHERE annotation_status = 'annotated'
            ORDER BY id
        """
    else:
        sql = """
            SELECT i.id, i.image_path, i.thumbnail_path
            FROM items i
            WHERE i.annotation_status = 'annotated'
              AND NOT EXISTS (
                SELECT 1 FROM item_image_embeddings e WHERE e.item_id = i.id
              )
            ORDER BY i.id
        """

    rows = conn.execute(sql).fetchall()
    total_available = len(rows)
    if args.limit and args.limit > 0:
        rows = rows[: int(args.limit)]

    print(
        f"[clip_embed_all] pending={total_available} will_process={len(rows)} "
        f"dry_run={args.dry_run} force={args.force}",
        flush=True,
    )

    ok = fail = 0
    for idx, row in enumerate(rows, start=1):
        item_id = int(row["id"])
        ref = pick_image_for_vision(row["thumbnail_path"], row["image_path"])
        if ref is None:
            print(f"[clip_embed_all] {idx}/{len(rows)} id={item_id} SKIP no_image_ref", flush=True)
            fail += 1
            continue

        if args.dry_run:
            kind = "path" if isinstance(ref, Path) else "url"
            print(f"[clip_embed_all] {idx}/{len(rows)} id={item_id} DRY-RUN {kind}={ref!r}", flush=True)
            continue

        try:
            vec = _embed_ref(ref)
            replace_item_image_embedding(conn, item_id, vec)
            conn.commit()
            print(f"[clip_embed_all] {idx}/{len(rows)} id={item_id} OK", flush=True)
            ok += 1
            time.sleep(0.05)
        except Exception as e:  # noqa: BLE001
            print(f"[clip_embed_all] {idx}/{len(rows)} id={item_id} FAIL {e!r}", file=sys.stderr, flush=True)
            fail += 1

    conn.close()
    print(f"[clip_embed_all] done ok={ok} fail={fail} dry_run={args.dry_run}", flush=True)
    return 0 if fail == 0 or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
