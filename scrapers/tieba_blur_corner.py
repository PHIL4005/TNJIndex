"""
Gaussian-blur the bottom-right corner of images (e.g. Tieba client watermark).

Scans ``--input-dir`` for supported images. Either write to ``--output-dir``
(preserving relative paths under the input root when ``--recursive``) or
overwrite originals with ``--in-place``. Applies ``ImageOps.exif_transpose``
first so "bottom-right" matches what you see in a viewer.

Usage::

    uv run python scrapers/tieba_blur_corner.py --input-dir data/staging/tieba/run1 \\
        --output-dir data/staging/tieba/run1_blurred
    uv run python scrapers/tieba_blur_corner.py --input-dir data/staging/tieba/run1 --in-place
    uv run python scrapers/tieba_blur_corner.py --input-dir data/staging/tieba/run1 --dry-run --output-dir /tmp/out
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
DEFAULT_WIDTH_FRAC = 0.22
DEFAULT_HEIGHT_FRAC = 0.10
DEFAULT_BLUR_RADIUS = 8.0
JPEG_QUALITY = 95

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


def _iter_images(input_dir: Path, *, recursive: bool) -> list[Path]:
    input_dir = input_dir.resolve()
    if not input_dir.is_dir():
        return []
    paths: list[Path] = []
    if recursive:
        for p in sorted(input_dir.rglob("*")):
            if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES:
                paths.append(p)
    else:
        for p in sorted(input_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES:
                paths.append(p)
    return paths


def _prepare_image(im: Image.Image) -> Image.Image:
    im = ImageOps.exif_transpose(im)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    return im.copy()


def _corner_box(w: int, h: int, width_frac: float, height_frac: float) -> tuple[int, int, int, int]:
    rw = max(1, round(w * width_frac))
    rh = max(1, round(h * height_frac))
    return (w - rw, h - rh, w, h)


def _blur_bottom_right(
    im: Image.Image,
    width_frac: float,
    height_frac: float,
    blur_radius: float,
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    w, h = im.size
    box = _corner_box(w, h, width_frac, height_frac)
    region = im.crop(box)
    blurred = region.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    out = im.copy()
    out.paste(blurred, box)
    return out, box


def _dest_path(
    src: Path,
    *,
    input_root: Path,
    in_place: bool,
    output_dir: Path,
) -> Path:
    if in_place:
        return src
    rel = src.resolve().relative_to(input_root.resolve())
    return output_dir / rel


def _save_image(im: Image.Image, dest: Path, original_format: str | None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    ext = dest.suffix.lower()
    if ext in (".jpg", ".jpeg") or (original_format or "").upper() == "JPEG":
        rgb = im.convert("RGB") if im.mode != "RGB" else im
        rgb.save(dest, "JPEG", quality=JPEG_QUALITY)
    elif ext == ".webp" or (original_format or "").upper() == "WEBP":
        im.save(dest, "WEBP", quality=JPEG_QUALITY)
    else:
        im.save(dest, "PNG")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Gaussian-blur bottom-right corner for all images under a directory.",
    )
    p.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        metavar="DIR",
        help="directory of source images",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help="write blurred images here (mirrors paths under --input-dir with --recursive)",
    )
    p.add_argument(
        "--in-place",
        action="store_true",
        help="overwrite each file under --input-dir",
    )
    p.add_argument(
        "--recursive",
        action="store_true",
        help="include images in subdirectories of --input-dir",
    )
    p.add_argument(
        "--width-frac",
        type=float,
        default=DEFAULT_WIDTH_FRAC,
        metavar="F",
        help=f"ROI width as fraction of image width (default {DEFAULT_WIDTH_FRAC})",
    )
    p.add_argument(
        "--height-frac",
        type=float,
        default=DEFAULT_HEIGHT_FRAC,
        metavar="F",
        help=f"ROI height as fraction of image height (default {DEFAULT_HEIGHT_FRAC})",
    )
    p.add_argument(
        "--blur-radius",
        type=float,
        default=DEFAULT_BLUR_RADIUS,
        metavar="R",
        help=f"GaussianBlur radius (default {DEFAULT_BLUR_RADIUS})",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="print actions only, do not write files",
    )
    args = p.parse_args(argv)

    if args.in_place and args.output_dir is not None:
        log.error("--in-place and --output-dir are mutually exclusive")
        return 2
    if not args.in_place and args.output_dir is None:
        log.error("specify either --output-dir or --in-place")
        return 2
    if args.width_frac <= 0 or args.width_frac > 1:
        log.error("--width-frac must be in (0, 1]")
        return 2
    if args.height_frac <= 0 or args.height_frac > 1:
        log.error("--height-frac must be in (0, 1]")
        return 2
    if args.blur_radius < 0:
        log.error("--blur-radius must be >= 0")
        return 2

    input_dir = args.input_dir.expanduser()
    if not input_dir.is_dir():
        log.error("input-dir is not a directory: %s", input_dir)
        return 2

    input_root = input_dir.resolve()
    paths = _iter_images(input_root, recursive=args.recursive)
    if not paths:
        log.error("no supported images under %s", input_root)
        return 2

    out_root: Path | None = None
    if args.output_dir is not None:
        out_root = args.output_dir.expanduser().resolve()
        if out_root == input_root and not args.dry_run:
            log.error("--output-dir must differ from --input-dir (use --in-place to overwrite)")
            return 2

    ok = 0
    skipped = 0
    for src in paths:
        dest = _dest_path(
            src,
            input_root=input_root,
            in_place=args.in_place,
            output_dir=out_root if out_root is not None else input_root,
        )

        try:
            with Image.open(src) as im0:
                orig_fmt = im0.format
                im = _prepare_image(im0)
            blurred, box = _blur_bottom_right(
                im,
                args.width_frac,
                args.height_frac,
                args.blur_radius,
            )
        except OSError as e:
            log.warning("skip (open/read failed) %s: %s", src, e)
            skipped += 1
            continue

        rw = box[2] - box[0]
        rh = box[3] - box[1]
        if args.dry_run:
            log.info(
                "dry-run %s -> %s ROI=%dx%d box=%s",
                src,
                dest,
                rw,
                rh,
                box,
            )
            ok += 1
            continue

        try:
            _save_image(blurred, dest, orig_fmt)
        except OSError as e:
            log.warning("skip (save failed) %s: %s", dest, e)
            skipped += 1
            continue

        log.info("wrote %s (ROI %dx%d)", dest, rw, rh)
        ok += 1

    log.info("done ok=%d skipped=%d", ok, skipped)
    return 0 if skipped == 0 or ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
