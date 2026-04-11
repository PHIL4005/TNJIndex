"""
Run Vision on a small DB sample and print JSONL for manual comparison (M1 / S2).

  uv run python -m pipelines.vision_eval --limit 12 --provider openai

Does not write to the database.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from pipelines.constants import REPO_ROOT
from pipelines.vision_client import Provider, annotate_image
from scrapers.db import get_conn


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env", override=False)
    except ImportError:
        pass


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    p = argparse.ArgumentParser(description="Vision sample eval → JSONL on stdout")
    p.add_argument("--limit", type=int, default=20, help="Number of items (default 20)")
    p.add_argument(
        "--provider",
        choices=("openai", "dashscope"),
        required=True,
        help="Which API to call",
    )
    args = p.parse_args(argv)

    os.environ["TNJ_VISION_PROVIDER"] = args.provider
    prov: Provider = args.provider

    if prov == "openai" and not os.environ.get("OPENAI_API_KEY"):
        print("[vision_eval] ERROR: OPENAI_API_KEY missing", file=sys.stderr)
        return 2
    if prov == "dashscope" and not os.environ.get("DASHSCOPE_API_KEY"):
        print("[vision_eval] ERROR: DASHSCOPE_API_KEY missing", file=sys.stderr)
        return 2

    conn = get_conn()
    rows = conn.execute(
        """
        SELECT id, image_path, thumbnail_path
        FROM items
        ORDER BY id
        LIMIT ?
        """,
        (args.limit,),
    ).fetchall()
    conn.close()

    from pipelines.paths import pick_image_path

    for row in rows:
        item_id = int(row["id"])
        path = pick_image_path(row["thumbnail_path"], row["image_path"])
        rec = {"item_id": item_id, "path": str(path) if path else None, "error": None, "data": None}
        if path is None or not path.is_file():
            rec["error"] = "missing_image"
        else:
            try:
                rec["data"] = annotate_image(path, provider=prov)
            except Exception as e:  # noqa: BLE001
                rec["error"] = repr(e)
        print(json.dumps(rec, ensure_ascii=False), flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
