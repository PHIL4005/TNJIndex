"""
Baidu Tieba — fetch thread images into a local staging directory for manual curation.

PC 端 ``/f?kw=`` 页面为 CSR 空壳（无 ``j_thread_list``），列表与楼层数据走贴吧客户端
protobuf 接口。本脚本通过 ``aiotieba`` 调用 ``tiebac.baidu.com`` 的 ``get_threads`` /
``get_posts`` 拉取帖子与图片 URL，再下载到本地。

Downloads images from a bar's thread list, writes ``manifest.jsonl`` (one JSON object
per line). After deleting unwanted files, ingest with::

    uv run python scrapers/ingest.py --dir <staging_dir> --source "tieba:<kw>"

**排序说明**: ``--sort reply``（按回复时间）在未登录时接口可能返回空列表，默认使用
``hot``。需要 ``reply`` 时请在 ``--cookie-file`` 中提供含 ``BDUSS`` 的 Cookie。

**依赖**: ``aiotieba``（见 ``pyproject.toml``）。

默认多翻列表页、多扫帖；每帖只保留按楼层顺序的**前 3 张**图（``--max-images-per-thread``，
``0`` 表示不限制）。可用 ``--pages`` / ``--max-threads`` 加大覆盖面。

Usage::

    uv run python scrapers/tieba_fetch.py --kw novelai --dry-run
    uv run python scrapers/tieba_fetch.py --kw novelai --out data/staging/tieba/run1
    uv run python scrapers/tieba_fetch.py --out data/staging/tieba/run1 --ingest
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import aiotieba as tb
import requests
from aiotieba.enums import PostSortType, ThreadSortType

from scrapers.ingest import ingest_image

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 60
THREADS_RN = 50  # get_threads 单次条数（最大 100）
PAGE_PC_REFERER = "https://tieba.baidu.com/"

ALLOWED_IMG_HOST_SUFFIXES = (
    "tiebapic.baidu.com",
    "imgsa.baidu.com",
    "hiphotos.baidu.com",
    "imgsrc.baidu.com",
    "img.baidu.com",
)

_SORT_ALIASES: dict[str, ThreadSortType] = {
    "hot": ThreadSortType.HOT,
    "reply": ThreadSortType.REPLY,
    "create": ThreadSortType.CREATE,
    "follow": ThreadSortType.FOLLOW,
}

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ThreadInfo:
    tid: int
    title: str
    reply_num: int

    @property
    def thread_url(self) -> str:
        return f"https://tieba.baidu.com/p/{self.tid}"


def polite_sleep(seconds_min: float, seconds_max: float) -> None:
    time.sleep(random.uniform(seconds_min, seconds_max))


def _session(cookie_file: Path | None) -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": PAGE_PC_REFERER,
        }
    )
    if cookie_file is not None and cookie_file.is_file():
        cookie = cookie_file.read_text(encoding="utf-8").strip()
        if cookie:
            s.headers["Cookie"] = cookie
            log.info("Loaded Cookie from %s", cookie_file)
    return s


def _parse_bduss_stoken(cookie_file: Path | None) -> tuple[str, str]:
    """Extract BDUSS / STOKEN from a browser Cookie header file (optional)."""
    if cookie_file is None or not cookie_file.is_file():
        return "", ""
    raw = cookie_file.read_text(encoding="utf-8").strip()
    if not raw:
        return "", ""
    bduss, stoken = "", ""
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _, value = part.partition("=")
        name, value = name.strip(), value.strip()
        if name == "BDUSS":
            bduss = value
        elif name == "STOKEN":
            stoken = value
    return bduss, stoken


def _host_allowed(netloc: str) -> bool:
    netloc = netloc.lower().split("@")[-1]
    if ":" in netloc:
        netloc = netloc.split(":")[0]
    return any(netloc == s or netloc.endswith("." + s) for s in ALLOWED_IMG_HOST_SUFFIXES)


def normalize_image_url(url: str) -> str | None:
    if not url or url.startswith("javascript:") or url.startswith("data:"):
        return None
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    if not url.startswith("http"):
        return None
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None
    if not _host_allowed(parsed.netloc):
        return None
    lower = url.lower()
    if "emoji" in lower or "emotion" in lower or "icon" in parsed.path:
        return None
    # 百度图床 / 贴吧 CDN 常靠 query（token、sign 等）鉴权；去掉 query 会统一返回占位小图。
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, "")
    )


def _norm_from_frag_image(img: object, min_side: int) -> str | None:
    """Pick CDN URL from aiotieba FragImage_*; respect min_side when dimensions known."""
    sw = getattr(img, "show_width", 0) or 0
    sh = getattr(img, "show_height", 0) or 0
    if sw and sh and min_side > 0 and min(sw, sh) < min_side:
        return None
    raw = (
        (getattr(img, "origin_src", None) or "")
        or (getattr(img, "big_src", None) or "")
        or (getattr(img, "src", None) or "")
    )
    return normalize_image_url(raw)


async def _gather_threads(
    client: tb.Client,
    kw: str,
    pages: int,
    min_replies: int,
    sort_type: ThreadSortType,
) -> list[ThreadInfo]:
    seen: set[int] = set()
    out: list[ThreadInfo] = []
    for pn in range(1, pages + 1):
        res = await client.get_threads(kw, pn=pn, rn=THREADS_RN, sort=sort_type)
        if res.err:
            log.warning("get_threads page %d: %s", pn, res.err)
            continue
        for th in res.objs:
            if th.tid in seen:
                continue
            seen.add(th.tid)
            out.append(
                ThreadInfo(
                    tid=int(th.tid),
                    title=(th.title or "").strip() or f"thread_{th.tid}",
                    reply_num=int(th.reply_num or 0),
                )
            )
        await asyncio.sleep(random.uniform(0.4, 1.0))

    filtered = [t for t in out if t.reply_num >= min_replies]
    filtered.sort(key=lambda t: t.reply_num, reverse=True)
    return filtered


async def _collect_image_urls_for_thread(
    client: tb.Client,
    tid: int,
    thread_pages: int,
    posts_rn: int,
    min_side: int,
    max_images: int | None,
) -> list[str]:
    """
    Floor order (ASC). If ``max_images`` is a positive int, stop once that many
    distinct URLs are collected (fewer get_posts pages).
    """
    ordered: list[str] = []
    seen: set[str] = set()
    cap = max_images if max_images and max_images > 0 else None
    for pn in range(1, thread_pages + 1):
        posts = await client.get_posts(
            tid,
            pn=pn,
            rn=posts_rn,
            sort=PostSortType.ASC,
            only_thread_author=False,
            with_comments=False,
        )
        if posts.err:
            log.warning("get_posts tid=%d pn=%d: %s", tid, pn, posts.err)
            break
        for post in posts.objs:
            for img in post.contents.imgs:
                u = _norm_from_frag_image(img, min_side)
                if u and u not in seen:
                    seen.add(u)
                    ordered.append(u)
                    if cap is not None and len(ordered) >= cap:
                        return ordered
        await asyncio.sleep(random.uniform(0.35, 0.9))
        if not posts.has_more:
            break
    return ordered


def download_binary(
    session: requests.Session,
    url: str,
    dest: Path,
    polite: bool,
    referer: str | None = None,
) -> bool:
    if polite:
        polite_sleep(0.5, 1.2)
    try:
        headers = {"Referer": referer} if referer else None
        r = session.get(url, timeout=REQUEST_TIMEOUT, stream=True, headers=headers)
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
        return dest.stat().st_size > 0
    except OSError as e:
        log.warning("[SKIP] write failed %s — %s", url, e)
        return False
    except requests.RequestException as e:
        log.warning("[SKIP] download failed %s — %s", url, e)
        return False


def _suffix_from_url(url: str) -> str:
    path = urlparse(url).path
    suf = Path(path).suffix.lower()
    if suf in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return ".jpg" if suf == ".jpeg" else suf
    return ".jpg"


async def _async_fetch_phase(
    kw: str,
    pages: int,
    max_threads: int,
    min_replies: int,
    thread_pages: int,
    posts_rn: int,
    min_side: int,
    sort_type: ThreadSortType,
    bduss: str,
    stoken: str,
    allow_empty_threads: bool,
    max_images_per_thread: int | None,
) -> tuple[list[ThreadInfo], list[ThreadInfo], dict[int, list[str]]]:
    async with tb.Client(BDUSS=bduss, STOKEN=stoken) as client:
        threads = await _gather_threads(client, kw, pages, min_replies, sort_type)
        picked: list[ThreadInfo] = []
        urls_by_tid: dict[int, list[str]] = {}
        for t in threads:
            if len(picked) >= max_threads:
                break
            urls = await _collect_image_urls_for_thread(
                client, t.tid, thread_pages, posts_rn, min_side, max_images_per_thread
            )
            await asyncio.sleep(random.uniform(0.2, 0.6))
            if not urls and not allow_empty_threads:
                continue
            picked.append(t)
            urls_by_tid[t.tid] = urls
        return threads, picked, urls_by_tid


def run_fetch(
    *,
    kw: str,
    pages: int,
    max_threads: int,
    min_replies: int,
    thread_pages: int,
    posts_rn: int,
    min_side: int,
    out_dir: Path,
    dry_run: bool,
    cookie_file: Path | None,
    sort_name: str,
    allow_empty_threads: bool,
    max_images_per_thread: int | None,
) -> None:
    sort_type = _SORT_ALIASES.get(sort_name.lower())
    if sort_type is None:
        log.error("Unknown --sort %r (use: hot, reply, create, follow)", sort_name)
        raise SystemExit(2)

    bduss, stoken = _parse_bduss_stoken(cookie_file)
    if bduss:
        log.info("Using BDUSS from cookie file for aiotieba client")
    session = _session(cookie_file)
    polite_dl = not dry_run

    threads, picked, urls_by_tid = asyncio.run(
        _async_fetch_phase(
            kw,
            pages,
            max_threads,
            min_replies,
            thread_pages,
            posts_rn,
            min_side,
            sort_type,
            bduss,
            stoken,
            allow_empty_threads,
            max_images_per_thread,
        )
    )

    if not picked:
        log.warning(
            "No threads returned (sort=%s). Try --sort hot or --sort create, "
            "or add BDUSS to --cookie-file for --sort reply.",
            sort_name,
        )

    log.info(
        "Threads after filter: %d candidate(s), using top %d (--max-threads)",
        len(threads),
        len(picked),
    )
    for t in picked:
        n = len(urls_by_tid.get(t.tid, []))
        log.info("  [%d replies] %s — %s (%d image URLs)", t.reply_num, t.tid, t.title[:80], n)

    if dry_run:
        total = sum(len(urls_by_tid.get(t.tid, [])) for t in picked)
        log.info("[dry-run] total image URLs ≈ %d (no files written)", total)
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.jsonl"
    url_seen: set[str] = set()
    seq_by_tid: dict[int, int] = {}

    with open(manifest_path, "w", encoding="utf-8") as mf:
        for t in picked:
            for url in urls_by_tid.get(t.tid, []):
                if url in url_seen:
                    continue
                url_seen.add(url)
                n = seq_by_tid.get(t.tid, 0)
                ext = _suffix_from_url(url)
                fname = f"{t.tid}_{n:04d}{ext}"
                dest = out_dir / fname
                if not download_binary(session, url, dest, polite=polite_dl, referer=t.thread_url):
                    continue
                seq_by_tid[t.tid] = n + 1
                record = {
                    "image_file": fname,
                    "image_url": url,
                    "thread_url": t.thread_url,
                    "thread_title": t.title,
                    "reply_num": t.reply_num,
                    "tid": t.tid,
                }
                mf.write(json.dumps(record, ensure_ascii=False) + "\n")
                mf.flush()
                log.info("[OK] %s", fname)

    log.info("Done. Staging: %s (manifest.jsonl)", out_dir.resolve())


def run_ingest_from_manifest(staging_dir: Path) -> None:
    manifest_path = staging_dir / "manifest.jsonl"
    if not manifest_path.is_file():
        log.error("No manifest.jsonl in %s", staging_dir)
        return
    ok, skipped = 0, 0
    with open(manifest_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            fname = rec.get("image_file")
            thread_url = rec.get("thread_url") or ""
            if not fname:
                continue
            path = staging_dir / fname
            if not path.is_file():
                log.warning("[SKIP] missing file: %s", fname)
                skipped += 1
                continue
            note = thread_url if thread_url else "tieba"
            item_id = ingest_image(path, source_note=note)
            if item_id is not None:
                ok += 1
            else:
                skipped += 1
    log.info("Ingest done: %d ok, %d skipped", ok, skipped)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Tieba bar → staging images + manifest.jsonl (via aiotieba)")
    p.add_argument("--kw", default="novelai", help="bar name (吧名 / fname)")
    p.add_argument(
        "--pages",
        type=int,
        default=2,
        help="forum list pages (get_threads pn); more = more thread candidates",
    )
    p.add_argument(
        "--max-threads",
        type=int,
        default=40,
        help="max threads to open (with images unless --allow-empty-threads)",
    )
    p.add_argument("--min-replies", type=int, default=0, help="minimum reply count")
    p.add_argument("--thread-pages", type=int, default=2, help="max get_posts pages per thread")
    p.add_argument(
        "--posts-rn",
        type=int,
        default=30,
        metavar="N",
        help="get_posts rn (floors per request, max 100)",
    )
    p.add_argument("--min-side", type=int, default=120, help="skip images when min(w,h) known and below this")
    p.add_argument(
        "--max-images-per-thread",
        type=int,
        default=3,
        metavar="N",
        help="first N images per thread (floor order); 0 = no limit",
    )
    p.add_argument(
        "--sort",
        dest="sort_name",
        default="hot",
        choices=sorted(_SORT_ALIASES.keys()),
        help="thread list sort (reply 未登录时可能为空，默认 hot)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="staging directory (default: data/staging/tieba/<timestamp>)",
    )
    p.add_argument("--dry-run", action="store_true", help="no downloads; print counts only")
    p.add_argument(
        "--cookie-file",
        type=Path,
        default=None,
        help="browser Cookie header; optional BDUSS/STOKEN improve auth-dependent sorts",
    )
    p.add_argument(
        "--ingest",
        action="store_true",
        help="read manifest.jsonl in --out and ingest each existing image into DB",
    )
    p.add_argument(
        "--allow-empty-threads",
        action="store_true",
        help="count threads with zero images toward --max-threads (default: skip them)",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.ingest:
        if args.out is None:
            log.error("--ingest requires --out <staging_dir>")
            raise SystemExit(1)
        run_ingest_from_manifest(args.out)
        raise SystemExit(0)

    root = Path(__file__).parent.parent
    default_staging = root / "data" / "staging" / "tieba"
    out = args.out
    if out is None:
        out = default_staging / time.strftime("%Y%m%d_%H%M%S")

    prn = max(2, min(100, args.posts_rn))
    cap = args.max_images_per_thread
    max_img = None if cap == 0 else max(1, cap)
    run_fetch(
        kw=args.kw,
        pages=max(1, args.pages),
        max_threads=max(1, args.max_threads),
        min_replies=max(0, args.min_replies),
        thread_pages=max(1, args.thread_pages),
        posts_rn=prn,
        min_side=max(0, args.min_side),
        out_dir=out,
        dry_run=args.dry_run,
        cookie_file=args.cookie_file,
        sort_name=args.sort_name,
        allow_empty_threads=args.allow_empty_threads,
        max_images_per_thread=max_img,
    )
