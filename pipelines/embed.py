"""
Batch text embedding for annotated items → item_embeddings.

  uv run python -m pipelines.embed --dry-run
  uv run python -m pipelines.embed --limit 50
  uv run python -m pipelines.embed --force

Uses TNJ_EMBED_PROVIDER / TNJ_EMBED_MODEL (see pipelines/embed_client.py).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

from sqlite_vec import serialize_float32

from pipelines.constants import REPO_ROOT
from pipelines.embed_client import Provider, embed_text
from pipelines.sqlite_vec import ensure_item_embeddings
from scrapers.db import get_conn


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env", override=False)
    except ImportError:
        pass


def _embed_input_text(description: str | None, tags_json: str) -> str:
    desc = (description or "").strip()
    try:
        tags_list: list[Any] = json.loads(tags_json or "[]")
    except json.JSONDecodeError:
        tags_list = []
    if not isinstance(tags_list, list):
        tags_list = []
    tag_str = " ".join(str(t).strip() for t in tags_list if str(t).strip())
    if desc and tag_str:
        return f"{desc} {tag_str}"
    return desc or tag_str or ""


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Embed annotated items into item_embeddings.")
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
        help="Re-embed items that already have a row in item_embeddings",
    )
    parser.add_argument(
        "--provider",
        choices=("openai", "dashscope"),
        default=None,
        help="Override TNJ_EMBED_PROVIDER",
    )
    args = parser.parse_args(argv)

    provider: Provider | None = args.provider
    if provider:
        os.environ["TNJ_EMBED_PROVIDER"] = provider

    if not args.dry_run:
        pv = (os.environ.get("TNJ_EMBED_PROVIDER") or os.environ.get("TNJ_VISION_PROVIDER") or "openai").lower()
        if pv == "dashscope" and not os.environ.get("DASHSCOPE_API_KEY"):
            print("[embed] ERROR: 缺少 DASHSCOPE_API_KEY", file=sys.stderr)
            return 2
        if pv != "dashscope" and not os.environ.get("OPENAI_API_KEY"):
            print("[embed] ERROR: 缺少 OPENAI_API_KEY（或设置 TNJ_EMBED_PROVIDER=dashscope）", file=sys.stderr)
            return 2

    conn = get_conn()
    ensure_item_embeddings(conn)

    if args.force:
        sql = """
            SELECT id, description, tags
            FROM items
            WHERE annotation_status = 'annotated'
            ORDER BY id
        """
    else:
        sql = """
            SELECT i.id, i.description, i.tags
            FROM items i
            WHERE i.annotation_status = 'annotated'
              AND NOT EXISTS (
                SELECT 1 FROM item_embeddings e WHERE e.item_id = i.id
              )
            ORDER BY i.id
        """

    rows = conn.execute(sql).fetchall()
    total_available = len(rows)
    if args.limit and args.limit > 0:
        rows = rows[: int(args.limit)]

    print(
        f"[embed] pending={total_available} will_process={len(rows)} dry_run={args.dry_run} force={args.force}",
        flush=True,
    )

    ok = fail = 0
    for idx, row in enumerate(rows, start=1):
        item_id = int(row["id"])
        text = _embed_input_text(row["description"], row["tags"])
        if not text.strip():
            print(f"[embed] {idx}/{len(rows)} id={item_id} SKIP empty_embed_text", flush=True)
            fail += 1
            continue

        if args.dry_run:
            print(f"[embed] {idx}/{len(rows)} id={item_id} DRY-RUN chars={len(text)}", flush=True)
            continue

        try:
            vec = embed_text(text, provider=provider)
            blob = serialize_float32(vec)
            conn.execute("DELETE FROM item_embeddings WHERE item_id = ?", (item_id,))
            conn.execute(
                "INSERT INTO item_embeddings(embedding, item_id) VALUES (?, ?)",
                (blob, item_id),
            )
            conn.commit()
            print(f"[embed] {idx}/{len(rows)} id={item_id} OK", flush=True)
            ok += 1
            time.sleep(0.05)
        except Exception as e:  # noqa: BLE001
            print(f"[embed] {idx}/{len(rows)} id={item_id} FAIL {e!r}", file=sys.stderr, flush=True)
            fail += 1

    conn.close()
    print(f"[embed] done ok={ok} fail={fail} dry_run={args.dry_run}", flush=True)
    return 0 if fail == 0 or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
