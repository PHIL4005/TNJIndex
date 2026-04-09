"""
Crawl Know Your Meme — Tom & Jerry photo gallery, download originals, ingest.

Gallery: https://knowyourmeme.com/memes/tom-and-jerry/photos?page=N
Each photo page exposes og:image (CDN URL). source_note = canonical photo page URL.

Usage:
    uv run python scrapers/kym.py --dry-run
    uv run python scrapers/kym.py [--limit N]
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from scrapers.db import get_all_source_notes, get_conn
from scrapers.ingest import ingest_image

GALLERY_BASE = "https://knowyourmeme.com/memes/tom-and-jerry/photos"
USER_AGENT = (
    "Mozilla/5.0 (compatible; TNJIndex/0.1; +https://github.com/; personal meme index project)"
)
REQUEST_TIMEOUT = 60
PHOTO_PATH_RE = re.compile(r"^/photos/(\d+)(?:-.+)?$")

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    return s


def canonical_photo_page_url(href: str) -> str | None:
    """Normalize gallery/photo links to https://knowyourmeme.com/photos/<id>-<slug>."""
    if not href:
        return None
    href = href.strip()
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    path = parsed.path.split("?")[0].rstrip("/") or ""
    if not path.startswith("/photos/"):
        return None
    m = PHOTO_PATH_RE.match(path)
    if not m:
        return None
    slug = path.removeprefix("/photos/")
    return f"https://knowyourmeme.com/photos/{slug}"


def normalize_source_note(note: str) -> str:
    """Map stored source_note to canonical photo URL when it is a KYM photo link."""
    c = canonical_photo_page_url(note)
    return c if c else note


def extract_photo_urls_from_gallery(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    seen: dict[str, None] = {}
    for a in soup.find_all("a", href=True):
        canon = canonical_photo_page_url(a["href"])
        if canon:
            seen.setdefault(canon, None)
    return list(seen.keys())


def fetch_og_image(session: requests.Session, photo_page_url: str) -> str | None:
    r = session.get(photo_page_url, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    og = soup.find("meta", property="og:image")
    if not og or not og.get("content"):
        return None
    return og["content"].strip()


def polite_sleep(seconds_min: float, seconds_max: float) -> None:
    time.sleep(random.uniform(seconds_min, seconds_max))


def download_image(session: requests.Session, image_url: str) -> Path:
    r = session.get(image_url, timeout=REQUEST_TIMEOUT, stream=True)
    r.raise_for_status()
    suffix = Path(urlparse(image_url).path).suffix.lower() or ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        suffix = ".jpg"
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    p = Path(path)
    try:
        with open(p, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
        return p
    except Exception:
        p.unlink(missing_ok=True)
        raise


def iter_gallery_pages(session: requests.Session, polite: bool) -> tuple[list[str], int]:
    """Fetch all gallery pages; return (all canonical photo URLs, pages_fetched)."""
    all_urls: list[str] = []
    page = 1
    pages_fetched = 0
    while True:
        if polite:
            polite_sleep(1.0, 2.0)
        url = f"{GALLERY_BASE}?page={page}"
        r = session.get(url, timeout=REQUEST_TIMEOUT)
        if r.status_code == 404:
            break
        r.raise_for_status()
        found = extract_photo_urls_from_gallery(r.text)
        pages_fetched += 1
        if not found:
            break
        all_urls.extend(found)
        page += 1
    # stable unique order
    uniq: dict[str, None] = {}
    for u in all_urls:
        uniq.setdefault(u, None)
    return list(uniq.keys()), pages_fetched


def run(*, dry_run: bool, limit: int | None) -> None:
    session = _session()
    polite = not dry_run

    log.info("Fetching gallery index…")
    photo_urls, n_pages = iter_gallery_pages(session, polite=polite)
    log.info("Gallery: %d page(s), %d unique photo URL(s)", n_pages, len(photo_urls))

    if dry_run:
        log.info("[dry-run] done (no downloads)")
        return

    conn = get_conn()
    try:
        existing_raw = get_all_source_notes(conn)
        existing = {normalize_source_note(s) for s in existing_raw}
    finally:
        conn.close()

    processed = 0
    ingested = 0
    for photo_url in photo_urls:
        if limit is not None and processed >= limit:
            break
        processed += 1

        if photo_url in existing:
            log.info("[SKIP] already in DB: %s", photo_url)
            continue

        try:
            if polite:
                polite_sleep(1.0, 2.0)
            image_url = fetch_og_image(session, photo_url)
            if not image_url:
                log.warning("[SKIP] no og:image: %s", photo_url)
                continue

            if polite:
                polite_sleep(1.0, 2.0)
            tmp = download_image(session, image_url)
            try:
                item_id = ingest_image(tmp, source_note=photo_url)
                if item_id is not None:
                    ingested += 1
                    existing.add(photo_url)
            finally:
                tmp.unlink(missing_ok=True)
        except Exception as e:
            log.error("[ERR] %s — %s", photo_url, e)

    log.info("Done: processed=%d, newly ingested=%d", processed, ingested)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="KYM Tom & Jerry gallery → ingest")
    p.add_argument("--dry-run", action="store_true", help="only list gallery count, no download")
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="stop after processing N gallery entries (including skips)",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(dry_run=args.dry_run, limit=args.limit)
