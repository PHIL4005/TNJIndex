"""
CLI semantic search (uses pipelines.search.search).

  uv run python -m pipelines.search_cli "汤姆假笑" --k 10
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from pipelines.constants import REPO_ROOT
from pipelines.embed_client import Provider
from pipelines.search import search


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env", override=False)
    except ImportError:
        pass


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Semantic search over indexed items.")
    parser.add_argument("query", nargs="?", default="", help="Search text")
    parser.add_argument("--k", type=int, default=10, help="Top-K (default 10)")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON instead of table",
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

    q = (args.query or "").strip()
    if not q:
        print("[search_cli] ERROR: empty query", file=sys.stderr)
        return 2

    pv = (os.environ.get("TNJ_EMBED_PROVIDER") or os.environ.get("TNJ_VISION_PROVIDER") or "openai").lower()
    if pv == "dashscope" and not os.environ.get("DASHSCOPE_API_KEY"):
        print("[search_cli] ERROR: 缺少 DASHSCOPE_API_KEY", file=sys.stderr)
        return 2
    if pv != "dashscope" and not os.environ.get("OPENAI_API_KEY"):
        print("[search_cli] ERROR: 缺少 OPENAI_API_KEY", file=sys.stderr)
        return 2

    rows = search(q, k=int(args.k), provider=provider)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    if not rows:
        print("[search_cli] (no results)")
        return 0

    for r in rows:
        tags_s = ", ".join(r["tags"][:8])
        if len(r["tags"]) > 8:
            tags_s += ", …"
        print(
            f"id={r['id']:>6}  score={r['score']:10.6f}  title={r['title']!r}  tags=[{tags_s}]",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
