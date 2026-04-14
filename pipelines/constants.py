"""Shared constants for pipelines (M1+)."""

from pathlib import Path

# Repository root (parent of pipelines/)
REPO_ROOT: Path = Path(__file__).resolve().parents[1]

# Placeholder / target embedding width for sqlite-vec `item_embeddings` (see tech_design §4).
# M2 embed.py must use the same dimension as the chosen embedding model.
EMBEDDING_DIM: int = 1536

# Jina CLIP v2 image vectors → sqlite-vec `item_image_embeddings` (see S2 以图搜图).
CLIP_IMAGE_EMBEDDING_DIM: int = 1024
DEFAULT_JINA_CLIP_MODEL: str = "jina-clip-v2"
JINA_EMBEDDINGS_URL: str = "https://api.jina.ai/v1/embeddings"

# Default text-embedding models (see pipelines/embed_client.py).
DEFAULT_EMBED_MODEL_OPENAI: str = "text-embedding-3-small"
# v3 在百炼侧最高 1024 维；为与 EMBEDDING_DIM=1536 对齐默认用 v4（可 TNJ_EMBED_MODEL 覆盖）。
DEFAULT_EMBED_MODEL_DASHSCOPE: str = "text-embedding-v4"
