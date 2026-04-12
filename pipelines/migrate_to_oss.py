"""
Upload local originals + thumbnails to Aliyun OSS (HK), then set DB paths to public URLs.

  uv run python -m pipelines.migrate_to_oss --dry-run
  uv run python -m pipelines.migrate_to_oss

Env（与仓库 `.env` 约定一致）：
  ALIYUN_OSS_ENDPOINT
  ALIYUN_OSS_BUCKET_NAME
  ALIYUN_OSS_ACCESS_KEY_ID / ALIYUN_OSS_ACCESS_KEY_SECRET
  ALIYUN_OSS_REGION（可选，默认 oss-cn-hongkong）

Object keys: originals/{basename}, thumbnails/{basename} (same filenames as locally).
"""

from __future__ import annotations

import argparse
import logging
import mimetypes
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from pipelines.constants import REPO_ROOT

log = logging.getLogger(__name__)

DEFAULT_ALIYUN_OSS_REGION = "oss-cn-hongkong"


def _oss_config_from_env() -> tuple[str, str, str, str, str]:
    """Returns endpoint, bucket, access_key_id, secret, region."""
    endpoint = (os.environ.get("ALIYUN_OSS_ENDPOINT") or "").strip().rstrip("/")
    bucket = (os.environ.get("ALIYUN_OSS_BUCKET_NAME") or "").strip()
    ak = (os.environ.get("ALIYUN_OSS_ACCESS_KEY_ID") or "").strip()
    sk = (os.environ.get("ALIYUN_OSS_ACCESS_KEY_SECRET") or "").strip()
    region = (os.environ.get("ALIYUN_OSS_REGION") or "").strip() or DEFAULT_ALIYUN_OSS_REGION
    return endpoint, bucket, ak, sk, region


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env", override=False)
    except ImportError:
        pass


def _public_base_url(bucket: str, region: str) -> str:
    return f"https://{bucket}.{region}.aliyuncs.com"


def _is_oss_item_url(value: str | None, bucket: str) -> bool:
    if not value or not str(value).strip():
        return False
    s = str(value).strip()
    if not s.lower().startswith("https://"):
        return False
    try:
        host = urlparse(s).netloc.lower()
    except ValueError:
        return False
    return bucket.lower() in host and "aliyuncs.com" in host


def _local_path(db_value: str) -> Path:
    p = Path(db_value.replace("\\", "/"))
    if p.is_absolute():
        return p
    return REPO_ROOT / p


def _guess_content_type(path: Path) -> str:
    mt, _ = mimetypes.guess_type(path.name)
    return mt or "application/octet-stream"


def _migrate(*, dry_run: bool, limit: int | None) -> int:
    _load_dotenv()
    endpoint, bucket_name, ak, sk, region = _oss_config_from_env()

    if not bucket_name:
        log.error(
            "缺少 ALIYUN_OSS_BUCKET_NAME（dry-run 也需要用于生成公开 URL）"
        )
        return 1

    if not dry_run:
        missing_labels: list[str] = []
        if not endpoint:
            missing_labels.append("ALIYUN_OSS_ENDPOINT")
        if not ak:
            missing_labels.append("ALIYUN_OSS_ACCESS_KEY_ID")
        if not sk:
            missing_labels.append("ALIYUN_OSS_ACCESS_KEY_SECRET")
        if missing_labels:
            log.error("缺少环境变量: %s", ", ".join(missing_labels))
            return 1

    public_base = _public_base_url(bucket_name, region)

    bucket = None
    if not dry_run:
        import oss2

        auth = oss2.Auth(ak, sk)
        bucket = oss2.Bucket(auth, endpoint, bucket_name)

    from scrapers.db import get_conn

    conn = get_conn()
    rows = conn.execute(
        "SELECT id, image_path, thumbnail_path FROM items ORDER BY id"
    ).fetchall()
    if limit is not None:
        rows = rows[:limit]

    updated = 0
    skipped = 0
    errors = 0

    for row in rows:
        iid = row["id"]
        image_path = row["image_path"] or ""
        thumb_raw = row["thumbnail_path"]
        thumb_path = str(thumb_raw).strip() if thumb_raw else ""

        need_image = not _is_oss_item_url(image_path, bucket_name)
        need_thumb = bool(thumb_path) and not _is_oss_item_url(thumb_path, bucket_name)

        if not need_image and not need_thumb:
            skipped += 1
            continue

        new_image = image_path
        new_thumb = thumb_raw

        try:
            if need_image:
                name = Path(image_path.replace("\\", "/")).name
                if not name:
                    log.error("[id=%s] image_path 无文件名: %r", iid, image_path)
                    errors += 1
                    continue
                key = f"originals/{name}"
                local = _local_path(image_path)
                if not local.is_file():
                    log.error("[id=%s] 原图不存在: %s", iid, local)
                    errors += 1
                    continue
                dest_url = f"{public_base}/{key}"
                if dry_run:
                    log.info("[DRY] id=%s put %s → %s", iid, local, dest_url)
                else:
                    assert bucket is not None
                    bucket.put_object_from_file(
                        key,
                        str(local),
                        headers={"Content-Type": _guess_content_type(local)},
                    )
                    log.info("[OK] id=%s image %s", iid, dest_url)
                new_image = dest_url

            if need_thumb:
                name_t = Path(thumb_path.replace("\\", "/")).name
                if not name_t:
                    log.error("[id=%s] thumbnail_path 无文件名: %r", iid, thumb_path)
                    errors += 1
                    continue
                key_t = f"thumbnails/{name_t}"
                local_t = _local_path(thumb_path)
                if not local_t.is_file():
                    log.error("[id=%s] 缩略图不存在: %s", iid, local_t)
                    errors += 1
                    continue
                dest_url_t = f"{public_base}/{key_t}"
                if dry_run:
                    log.info("[DRY] id=%s put %s → %s", iid, local_t, dest_url_t)
                else:
                    assert bucket is not None
                    bucket.put_object_from_file(
                        key_t,
                        str(local_t),
                        headers={"Content-Type": _guess_content_type(local_t)},
                    )
                    log.info("[OK] id=%s thumb %s", iid, dest_url_t)
                new_thumb = dest_url_t

            if dry_run:
                updated += 1
            else:
                conn.execute(
                    "UPDATE items SET image_path = ?, thumbnail_path = ? WHERE id = ?",
                    (new_image, new_thumb, iid),
                )
                conn.commit()
                updated += 1
        except Exception as e:  # noqa: BLE001
            log.exception("[id=%s] 失败: %s", iid, e)
            errors += 1

    conn.close()
    log.info("完成: updated=%d skipped=%d errors=%d dry_run=%s", updated, skipped, errors, dry_run)
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description="Migrate local images to Aliyun OSS HK and update DB.")
    p.add_argument("--dry-run", action="store_true", help="只打印将执行的操作，不上传、不写库")
    p.add_argument("--limit", type=int, default=None, help="最多处理 N 条（调试用）")
    args = p.parse_args(argv)
    return _migrate(dry_run=args.dry_run, limit=args.limit)


if __name__ == "__main__":
    sys.exit(main())
