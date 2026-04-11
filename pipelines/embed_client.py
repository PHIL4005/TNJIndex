"""Text embedding API (OpenAI + DashScope) for sqlite-vec row width."""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import Literal

from pipelines.constants import (
    DEFAULT_EMBED_MODEL_DASHSCOPE,
    DEFAULT_EMBED_MODEL_OPENAI,
    EMBEDDING_DIM,
)

Provider = Literal["openai", "dashscope"]


def _embed_provider_from_env() -> Provider:
    v = (os.environ.get("TNJ_EMBED_PROVIDER") or os.environ.get("TNJ_VISION_PROVIDER") or "openai").strip().lower()
    if v in ("openai", "dashscope"):
        return v  # type: ignore[return-value]
    raise ValueError(f"TNJ_EMBED_PROVIDER must be openai or dashscope, got: {v!r}")


def _model_for(provider: Provider) -> str:
    override = os.environ.get("TNJ_EMBED_MODEL")
    if override:
        return override.strip()
    if provider == "openai":
        return DEFAULT_EMBED_MODEL_OPENAI
    return DEFAULT_EMBED_MODEL_DASHSCOPE


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


def _call_openai_embed(text: str, *, model: str) -> list[float]:
    _require_openai_key()
    from openai import OpenAI

    client = OpenAI()
    resp = client.embeddings.create(
        model=model,
        input=text,
        dimensions=EMBEDDING_DIM,
    )
    vec = resp.data[0].embedding
    if len(vec) != EMBEDDING_DIM:
        raise RuntimeError(f"openai_embedding_dim_mismatch: expected {EMBEDDING_DIM}, got {len(vec)}")
    return list(vec)


def _call_dashscope_embed(text: str, *, model: str) -> list[float]:
    _require_dashscope_key()
    from dashscope import TextEmbedding

    # DashScope: v4 supports dimension=1536; v3 最高 1024，与 sqlite-vec 表宽对齐用 v4 默认
    resp = TextEmbedding.call(
        model=model,
        input=text,
        dimension=EMBEDDING_DIM,
    )
    if resp.status_code != HTTPStatus.OK:
        raise RuntimeError(
            f"dashscope_embed_http_{resp.status_code}: {getattr(resp, 'message', resp)}"
        )
    out = resp.output
    if not out or "embeddings" not in out:
        raise RuntimeError("dashscope_embed_empty_output")
    emb = out["embeddings"][0]
    vec = emb.get("embedding") if isinstance(emb, dict) else getattr(emb, "embedding", None)
    if not isinstance(vec, list):
        raise RuntimeError("dashscope_embed_bad_embedding_field")
    if len(vec) != EMBEDDING_DIM:
        raise RuntimeError(f"dashscope_embedding_dim_mismatch: expected {EMBEDDING_DIM}, got {len(vec)}")
    return [float(x) for x in vec]


def embed_text(
    text: str,
    *,
    provider: Provider | None = None,
    model: str | None = None,
) -> list[float]:
    """
    Return a single embedding vector (length EMBEDDING_DIM).

    Provider: TNJ_EMBED_PROVIDER or fallback TNJ_VISION_PROVIDER (default openai).
    """
    pv = provider or _embed_provider_from_env()
    md = model or _model_for(pv)
    if pv == "openai":
        return _call_openai_embed(text, model=md)
    return _call_dashscope_embed(text, model=md)
