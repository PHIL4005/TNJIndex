"""
Batch Vision annotation: raw → annotated.

  uv run python -m pipelines.annotate --limit 20
  uv run python -m pipelines.annotate --limit 5 --dry-run

Requires OPENAI_API_KEY or DASHSCOPE_API_KEY per TNJ_VISION_PROVIDER.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from pipelines.constants import REPO_ROOT
from pipelines.paths import pick_image_path
from pipelines.sqlite_vec import ensure_item_embeddings
from pipelines.vision_client import Provider, annotate_image
from scrapers.db import get_conn, update_annotation


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env", override=False)
    except ImportError:
        pass


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Vision-annotate raw items.")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max raw items to process (default 0 = all remaining raw)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions only, no API/DB writes")
    parser.add_argument(
        "--provider",
        choices=("openai", "dashscope"),
        default=None,
        help="Override TNJ_VISION_PROVIDER",
    )
    args = parser.parse_args(argv)

    provider: Provider | None = args.provider
    if provider:
        os.environ["TNJ_VISION_PROVIDER"] = provider

    # Fail fast on missing credentials (unless dry-run for listing)
    if not args.dry_run:
        pv = (os.environ.get("TNJ_VISION_PROVIDER") or "openai").lower()
        if pv == "dashscope" and not os.environ.get("DASHSCOPE_API_KEY"):
            print("[annotate] ERROR: 缺少 DASHSCOPE_API_KEY", file=sys.stderr)
            return 2
        if pv != "dashscope" and not os.environ.get("OPENAI_API_KEY"):
            print("[annotate] ERROR: 缺少 OPENAI_API_KEY（或设置 TNJ_VISION_PROVIDER=dashscope）", file=sys.stderr)
            return 2

    conn = get_conn()
    if not args.dry_run:
        ensure_item_embeddings(conn)

    if args.limit and args.limit > 0:
        rows = conn.execute(
            """
            SELECT id, image_path, thumbnail_path, annotation_status
            FROM items
            WHERE annotation_status = 'raw'
            ORDER BY id
            LIMIT ?
            """,
            (int(args.limit),),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, image_path, thumbnail_path, annotation_status
            FROM items
            WHERE annotation_status = 'raw'
            ORDER BY id
            """
        ).fetchall()
    total = len(rows)
    ok = fail = 0

    for idx, row in enumerate(rows, start=1):
        item_id = int(row["id"])
        img_path = pick_image_path(row["thumbnail_path"], row["image_path"])
        if img_path is None or not img_path.is_file():
            print(f"[annotate] {idx}/{total} id={item_id} SKIP missing_image", flush=True)
            fail += 1
            continue

        if args.dry_run:
            print(f"[annotate] {idx}/{total} id={item_id} DRY-RUN would_call {img_path}", flush=True)
            continue

        try:
            data = annotate_image(img_path, provider=provider)
            update_annotation(conn, item_id, data["title"], data["tags"], data["description"])
            print(
                f"[annotate] {idx}/{total} id={item_id} OK title={data['title']!r}",
                flush=True,
            )
            ok += 1
            time.sleep(0.15)
        except Exception as e:  # noqa: BLE001
            print(f"[annotate] {idx}/{total} id={item_id} FAIL {e!r}", file=sys.stderr, flush=True)
            fail += 1

    conn.close()
    print(f"[annotate] done ok={ok} fail={fail} dry_run={args.dry_run}", flush=True)
    return 0 if fail == 0 or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
