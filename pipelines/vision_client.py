"""Vision API calls for image → structured JSON (title / tags / description)."""

from __future__ import annotations

import base64
import mimetypes
import os
import time
from pathlib import Path
from typing import Any, Literal

from pipelines.annotation_validate import parse_vision_json, validate_annotation
from pipelines.paths import is_http_url
from pipelines.prompts import VISION_ANNOTATION_PROMPT

Provider = Literal["openai", "dashscope"]

DEFAULT_MODEL_OPENAI = "gpt-4o"
DEFAULT_MODEL_DASHSCOPE = "qwen3.6-plus"


def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "image/jpeg"


def _read_image_data_url(path: Path) -> str:
    raw = path.read_bytes()
    b64 = base64.standard_b64encode(raw).decode("ascii")
    mime = _guess_mime(path)
    return f"data:{mime};base64,{b64}"


def _openai_image_url(image_ref: Path | str) -> str:
    """Return URL for OpenAI ``image_url`` (data URL for local file, passthrough for http)."""
    if isinstance(image_ref, Path):
        return _read_image_data_url(image_ref)
    return image_ref


def _provider_from_env() -> Provider:
    v = (os.environ.get("TNJ_VISION_PROVIDER") or "openai").strip().lower()
    if v in ("openai", "dashscope"):
        return v  # type: ignore[return-value]
    raise ValueError(f"TNJ_VISION_PROVIDER must be openai or dashscope, got: {v!r}")


def _model_for(provider: Provider) -> str:
    override = os.environ.get("TNJ_VISION_MODEL")
    if override:
        return override.strip()
    if provider == "openai":
        return DEFAULT_MODEL_OPENAI
    return DEFAULT_MODEL_DASHSCOPE


def _require_openai_key() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "缺少环境变量 OPENAI_API_KEY。请 export OPENAI_API_KEY=... 或在仓库根目录放置 .env"
        )


def _require_dashscope_key() -> None:
    if not os.environ.get("DASHSCOPE_API_KEY"):
        raise RuntimeError(
            "缺少环境变量 DASHSCOPE_API_KEY。请 export DASHSCOPE_API_KEY=... 或在仓库根目录放置 .env"
        )


def _call_openai(image_ref: Path | str, *, model: str, max_retries: int = 3) -> str:
    _require_openai_key()
    from openai import OpenAI

    client = OpenAI()
    img_url = _openai_image_url(image_ref)
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": VISION_ANNOTATION_PROMPT},
                            {"type": "image_url", "image_url": {"url": img_url}},
                        ],
                    }
                ],
            )
            choice = resp.choices[0].message
            content = choice.content or ""
            return content
        except Exception as e:  # noqa: BLE001 — surface last error after retries
            code = getattr(e, "status_code", None) or getattr(e, "code", None)
            retriable = code in (429, 500, 502, 503, 504) or "rate" in str(e).lower()
            if attempt + 1 < max_retries and retriable:
                time.sleep(2**attempt)
                continue
            raise
    raise RuntimeError("openai_call_failed")


def _call_dashscope(image_ref: Path | str, *, model: str, max_retries: int = 3) -> str:
    _require_dashscope_key()
    from http import HTTPStatus

    from dashscope import MultiModalConversation

    if isinstance(image_ref, Path):
        image_spec: str = f"file://{image_ref.resolve()}"
    elif is_http_url(image_ref):
        image_spec = image_ref
    else:
        raise RuntimeError(f"dashscope: unsupported image_ref type: {type(image_ref)!r}")

    for attempt in range(max_retries):
        try:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"image": image_spec},
                        {"text": VISION_ANNOTATION_PROMPT},
                    ],
                }
            ]
            resp = MultiModalConversation.call(model=model, messages=messages)
            if resp.status_code != HTTPStatus.OK:
                raise RuntimeError(
                    f"dashscope_http_{resp.status_code}: {getattr(resp, 'message', resp)}"
                )
            content_chunks = resp.output.choices[0].message.content
            if isinstance(content_chunks, list):
                parts = []
                for block in content_chunks:
                    if isinstance(block, dict) and "text" in block:
                        parts.append(str(block["text"]))
                    elif isinstance(block, str):
                        parts.append(block)
                return "\n".join(parts).strip()
            return str(content_chunks)
        except Exception:  # noqa: BLE001
            if attempt + 1 < max_retries:
                time.sleep(2**attempt)
                continue
            raise
    raise RuntimeError("dashscope_call_failed")


def annotate_image(
    image_ref: Path | str,
    *,
    provider: Provider | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """
    Call Vision API and return a validated dict with title, tags, description.

    ``image_ref`` may be a local ``Path`` (file must exist) or an ``http(s)`` URL
    (e.g. public OSS thumbnail/original).

    Raises RuntimeError on API/parse/validation failure.
    """
    pv = provider or _provider_from_env()
    md = model or _model_for(pv)
    if pv == "openai":
        raw = _call_openai(image_ref, model=md)
    else:
        raw = _call_dashscope(image_ref, model=md)

    data, err = parse_vision_json(raw)
    if err or data is None:
        raise RuntimeError(err or "parse_failed")

    ok, reason = validate_annotation(data)
    if not ok:
        raise RuntimeError(f"validation_failed:{reason}")

    return {
        "title": data["title"],
        "tags": data["tags"],
        "description": data["description"],
    }
