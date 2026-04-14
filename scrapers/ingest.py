"""
Ingest pipeline: normalize → thumbnail → pHash dedup → write DB.

Usage (single file):
    uv run python scrapers/ingest.py <image_path> [--source <url>]

Usage (batch directory):
    uv run python scrapers/ingest.py --dir <directory> [--source <note>]
"""

import argparse
import logging
from pathlib import Path

import imagehash
from PIL import Image

from pipelines.clip_embed import index_item_image
from pipelines.sqlite_vec import ensure_item_image_embeddings
from scrapers.db import get_all_phashes, get_conn, insert_item

ORIGINALS_DIR = Path(__file__).parent.parent / "data" / "images" / "originals"
THUMBNAILS_DIR = Path(__file__).parent.parent / "data" / "images" / "thumbnails"

PHASH_THRESHOLD = 8
THUMB_MAX_SIDE = 400
THUMB_QUALITY = 75
ORIGINAL_QUALITY = 95
SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


def _next_seq(conn) -> int:
    row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM items").fetchone()
    return row[0] + 1


def _make_thumbnail(src: Path, dest: Path) -> None:
    with Image.open(src) as img:
        img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > THUMB_MAX_SIDE:
            ratio = THUMB_MAX_SIDE / max(w, h)
            new_size = (int(w * ratio), int(h * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        img.save(dest, "JPEG", quality=THUMB_QUALITY)


def _compute_phash(path: Path) -> imagehash.ImageHash:
    with Image.open(path) as img:
        return imagehash.phash(img)


def _is_duplicate(new_hash: imagehash.ImageHash, stored: list[str]) -> bool:
    for h in stored:
        if new_hash - imagehash.hex_to_hash(h) <= PHASH_THRESHOLD:
            return True
    return False


def ingest_image(src_path: "str | Path", source_note: "str | None" = None) -> "int | None":
    """
    Ingest a single image file.

    Returns the new item id on success, or None if the image was skipped (duplicate
    or unsupported format).
    """
    src = Path(src_path)
    if src.suffix.lower() not in SUPPORTED_SUFFIXES:
        log.warning("[SKIP] unsupported format: %s", src.name)
        return None

    ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
    THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_conn()
    try:
        seq = _next_seq(conn)
        stored_hashes = get_all_phashes(conn)
        new_hash = _compute_phash(src)

        if _is_duplicate(new_hash, stored_hashes):
            log.info("[SKIP] duplicate: %s", src.name)
            return None

        filename = f"image_{seq:05d}.jpg"
        dest_original = ORIGINALS_DIR / filename
        dest_thumb = THUMBNAILS_DIR / filename
        repo_root = Path(__file__).parent.parent
        rel_original = str(dest_original.relative_to(repo_root))
        rel_thumb = str(dest_thumb.relative_to(repo_root))

        with Image.open(src) as img:
            img.convert("RGB").save(dest_original, "JPEG", quality=ORIGINAL_QUALITY)

        _make_thumbnail(dest_original, dest_thumb)

        item_id = insert_item(
            conn,
            image_path=rel_original,
            thumbnail_path=rel_thumb,
            source_note=source_note,
            phash=str(new_hash),
        )
        ensure_item_image_embeddings(conn)
        index_item_image(
            conn,
            item_id=item_id,
            thumbnail_path=rel_thumb,
            image_path=rel_original,
        )
        log.info("[OK] ingested: %s → id=%d (%s)", src.name, item_id, filename)
        return item_id
    finally:
        conn.close()


def _ingest_dir(directory: Path, source_note: "str | None") -> None:
    files = sorted(
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    )
    log.info("Found %d image(s) in %s", len(files), directory)
    ok, skipped = 0, 0
    for f in files:
        result = ingest_image(f, source_note=source_note)
        if result is not None:
            ok += 1
        else:
            skipped += 1
    log.info("Done: %d ingested, %d skipped", ok, skipped)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest image(s) into TNJIndex.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("image", nargs="?", help="Path to a single image file")
    group.add_argument("--dir", metavar="DIR", help="Directory of images to ingest in batch")
    parser.add_argument("--source", metavar="NOTE", default=None, help="source_note for all ingested items")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.dir:
        _ingest_dir(Path(args.dir), source_note=args.source)
    else:
        ingest_image(args.image, source_note=args.source)
