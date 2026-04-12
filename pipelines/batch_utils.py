"""
DashScope Batch File API helpers for Vision annotation.

Flow:
  1. Build JSONL (one request per item, base64 image + prompt)
  2. Upload JSONL to DashScope Files API (purpose="batch")
  3. Create Batch job (endpoint="/v1/chat/completions", completion_window="24h")
  4. Poll until completed / failed / expired
  5. Download output JSONL, parse + validate + write to DB
  6. Print summary; log error_file_id details if present

Requires DASHSCOPE_API_KEY and openai Python SDK (used in OpenAI-compat mode).
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import tempfile
import time
from typing import Any

from pipelines.annotation_validate import parse_vision_json, validate_annotation
from pipelines.paths import pick_image_path
from pipelines.prompts import VISION_ANNOTATION_PROMPT
from pipelines.vision_client import _read_image_data_url  # reuse base64 encoder
from scrapers.db import update_annotation

DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_POLL_INTERVAL_INIT = 30   # seconds
_POLL_INTERVAL_MAX = 300   # 5 minutes cap
_TERMINAL_STATUSES = {"completed", "failed", "expired", "cancelled"}


def _get_model() -> str:
    override = os.environ.get("TNJ_VISION_MODEL")
    if override:
        return override.strip()
    from pipelines.vision_client import DEFAULT_MODEL_DASHSCOPE
    return DEFAULT_MODEL_DASHSCOPE


def _build_jsonl(rows: list[sqlite3.Row]) -> str:
    """Build JSONL string: one request per row, image as base64 data-URL."""
    model = _get_model()
    lines: list[str] = []
    skipped = 0

    for row in rows:
        item_id = int(row["id"])
        img_path = pick_image_path(row["thumbnail_path"], row["image_path"])
        if img_path is None or not img_path.is_file():
            print(f"[batch] id={item_id} SKIP missing_image", flush=True)
            skipped += 1
            continue

        data_url = _read_image_data_url(img_path)
        body: dict[str, Any] = {
            "model": model,
            "response_format": {"type": "json_object"},
            "enable_thinking": False,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": VISION_ANNOTATION_PROMPT},
                    ],
                }
            ],
        }
        request = {
            "custom_id": str(item_id),
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": body,
        }
        lines.append(json.dumps(request, ensure_ascii=False, separators=(",", ":")))

    if skipped:
        print(f"[batch] build_jsonl: skipped {skipped} items (missing image)", flush=True)

    return "\n".join(lines)


def _make_client():
    from openai import OpenAI
    return OpenAI(
        api_key=os.environ["DASHSCOPE_API_KEY"],
        base_url=DASHSCOPE_BASE_URL,
    )


def _upload_jsonl(client, jsonl_content: str) -> str:
    """Upload JSONL bytes, return file_id."""
    print("[batch] uploading JSONL...", flush=True)
    file_bytes = jsonl_content.encode("utf-8")
    file_obj = client.files.create(
        file=("batch_annotate.jsonl", io.BytesIO(file_bytes), "application/jsonl"),
        purpose="batch",
    )
    print(f"[batch] uploaded file_id={file_obj.id}", flush=True)
    return file_obj.id


def _create_batch(client, file_id: str) -> str:
    """Create batch job, return batch_id."""
    model = _get_model()
    batch = client.batches.create(
        input_file_id=file_id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
        metadata={
            "ds_name": f"tnjindex_annotate_{int(time.time())}",
            "ds_description": f"TNJIndex Vision annotation ({model})",
        },
    )
    print(f"[batch] created batch_id={batch.id} status={batch.status}", flush=True)
    return batch.id


def _poll_until_done(client, batch_id: str) -> Any:
    """Poll batch status until terminal; return final batch object."""
    interval = _POLL_INTERVAL_INIT
    poll_count = 0
    while True:
        time.sleep(interval)
        batch = client.batches.retrieve(batch_id)
        poll_count += 1
        counts = batch.request_counts
        print(
            f"[batch] poll #{poll_count} status={batch.status} "
            f"completed={counts.completed}/{counts.total} failed={counts.failed}",
            flush=True,
        )
        if batch.status in _TERMINAL_STATUSES:
            return batch
        interval = min(interval * 1.5, _POLL_INTERVAL_MAX)


def _parse_and_write(client, conn: sqlite3.Connection, batch) -> tuple[int, int]:
    """Download results, validate, write to DB. Returns (ok, fail)."""
    ok = fail = 0

    if batch.status != "completed":
        print(f"[batch] batch ended with status={batch.status}, no results to write", file=__import__("sys").stderr, flush=True)
        return 0, 0

    # Download success results
    if batch.output_file_id:
        content = client.files.content(batch.output_file_id)
        result_text = content.text
        for line in result_text.splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                item_id = int(rec["custom_id"])
                response_body = rec.get("response", {}).get("body", {})
                raw_content = response_body.get("choices", [{}])[0].get("message", {}).get("content", "")

                data, err = parse_vision_json(raw_content)
                if err or data is None:
                    print(f"[batch] id={item_id} parse_fail: {err}", file=__import__("sys").stderr, flush=True)
                    fail += 1
                    continue

                valid, reason = validate_annotation(data)
                if not valid:
                    print(f"[batch] id={item_id} validate_fail: {reason}", file=__import__("sys").stderr, flush=True)
                    fail += 1
                    continue

                update_annotation(conn, item_id, data["title"], data["tags"], data["description"])
                print(f"[batch] id={item_id} OK title={data['title']!r}", flush=True)
                ok += 1
            except Exception as e:  # noqa: BLE001
                print(f"[batch] line parse error: {e!r} line={line[:120]}", file=__import__("sys").stderr, flush=True)
                fail += 1

    # Log error details
    if batch.error_file_id:
        print(f"[batch] error_file_id={batch.error_file_id} — downloading error details...", flush=True)
        err_content = client.files.content(batch.error_file_id)
        for line in err_content.text.splitlines():
            if line.strip():
                print(f"[batch][error] {line}", file=__import__("sys").stderr, flush=True)
                fail += 1

    return ok, fail


def run_batch_annotate(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
    dry_run: bool = False,
) -> tuple[int, int]:
    """Full batch annotation flow. Returns (ok, fail)."""
    jsonl = _build_jsonl(rows)
    line_count = sum(1 for l in jsonl.splitlines() if l.strip())
    print(f"[batch] JSONL ready: {line_count} requests", flush=True)

    if dry_run:
        print(f"[batch] DRY-RUN: would submit {line_count} requests via Batch API", flush=True)
        return 0, 0

    if line_count == 0:
        print("[batch] no valid requests to submit", flush=True)
        return 0, 0

    client = _make_client()
    file_id = _upload_jsonl(client, jsonl)
    batch_id = _create_batch(client, file_id)

    print(f"[batch] waiting for batch {batch_id}...", flush=True)
    batch = _poll_until_done(client, batch_id)
    print(f"[batch] final status={batch.status}", flush=True)

    ok, fail = _parse_and_write(client, conn, batch)
    print(
        f"[batch] summary ok={ok} fail={fail} "
        "(Batch 费率约实时 50%，实际以阿里云控制台账单为准)",
        flush=True,
    )
    return ok, fail
