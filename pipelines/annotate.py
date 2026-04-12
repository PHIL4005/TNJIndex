"""
Batch Vision annotation: raw → annotated.

  uv run python -m pipelines.annotate --limit 20
  uv run python -m pipelines.annotate --limit 5 --dry-run
  uv run python -m pipelines.annotate --force --limit 10          # re-annotate annotated items
  uv run python -m pipelines.annotate --force --enable-batch      # DashScope Batch API (50% cost)

Requires OPENAI_API_KEY or DASHSCOPE_API_KEY per TNJ_VISION_PROVIDER.

Images: ``pick_image_for_vision`` uses local ``data/images/...`` when present, else public ``https://`` URLs from DB (e.g. OSS) for Vision APIs.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from pipelines.constants import REPO_ROOT
from pipelines.paths import pick_image_for_vision
from pipelines.sqlite_vec import ensure_item_embeddings
from pipelines.vision_client import Provider, annotate_image
from scrapers.db import get_conn, update_annotation


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env", override=False)
    except ImportError:
        pass


def _select_rows(conn, force: bool, limit: int):
    status_clause = "annotation_status IN ('raw', 'annotated')" if force else "annotation_status = 'raw'"
    sql = f"""
        SELECT id, image_path, thumbnail_path, annotation_status
        FROM items
        WHERE {status_clause}
        ORDER BY id
    """
    if limit and limit > 0:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql).fetchall()


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Vision-annotate items.")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max items to process (default 0 = all)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions only, no API/DB writes")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Also re-annotate already-annotated items (default: only raw)",
    )
    parser.add_argument(
        "--enable-batch",
        action="store_true",
        help="Use DashScope Batch File API (async, ~50%% cost vs real-time; dashscope provider only)",
    )
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

    pv = (os.environ.get("TNJ_VISION_PROVIDER") or "openai").lower()

    if args.enable_batch and pv != "dashscope":
        print("[annotate] ERROR: --enable-batch 仅支持 dashscope provider", file=sys.stderr)
        return 2

    # Fail fast on missing credentials (unless dry-run)
    if not args.dry_run:
        if pv == "dashscope" and not os.environ.get("DASHSCOPE_API_KEY"):
            print("[annotate] ERROR: 缺少 DASHSCOPE_API_KEY", file=sys.stderr)
            return 2
        if pv != "dashscope" and not os.environ.get("OPENAI_API_KEY"):
            print("[annotate] ERROR: 缺少 OPENAI_API_KEY（或设置 TNJ_VISION_PROVIDER=dashscope）", file=sys.stderr)
            return 2

    conn = get_conn()
    if not args.dry_run:
        ensure_item_embeddings(conn)

    rows = _select_rows(conn, force=args.force, limit=args.limit)
    total = len(rows)
    print(f"[annotate] selected={total} force={args.force} batch={args.enable_batch} dry_run={args.dry_run}", flush=True)

    if total == 0:
        print("[annotate] nothing to do", flush=True)
        conn.close()
        return 0

    if args.enable_batch:
        from pipelines.batch_utils import run_batch_annotate
        ok, fail = run_batch_annotate(conn, rows, dry_run=args.dry_run)
        conn.close()
        print(f"[annotate] done ok={ok} fail={fail} batch=True", flush=True)
        return 0 if fail == 0 or args.dry_run else 1

    # --- real-time path ---
    ok = fail = 0
    for idx, row in enumerate(rows, start=1):
        item_id = int(row["id"])
        img_ref = pick_image_for_vision(row["thumbnail_path"], row["image_path"])
        if img_ref is None:
            print(f"[annotate] {idx}/{total} id={item_id} SKIP missing_image", flush=True)
            fail += 1
            continue

        if args.dry_run:
            print(f"[annotate] {idx}/{total} id={item_id} DRY-RUN would_call {img_ref!r}", flush=True)
            continue

        try:
            data = annotate_image(img_ref, provider=provider)
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
