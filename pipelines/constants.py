"""Shared constants for pipelines (M1+)."""

from pathlib import Path

# Repository root (parent of pipelines/)
REPO_ROOT: Path = Path(__file__).resolve().parents[1]

# Placeholder / target embedding width for sqlite-vec `item_embeddings` (see tech_design §4).
# M2 embed.py must use the same dimension as the chosen embedding model.
EMBEDDING_DIM: int = 1536
