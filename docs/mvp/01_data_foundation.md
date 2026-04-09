# Phase 01 — 数据基础

> 状态: 进行中（S1～S2 已完成）| 依赖: `tech_design` §1 §2 定稿  
> 目标: 定义 Item Schema，跑通采集 → 入库；本地库 ≥ 500 条规范化 Item。

---

## 步骤总览

| # | 步骤 | 产出 | 验收方式 |
|---|------|------|---------|
| S1 | 项目初始化 ✅ | Python 骨架 + 目录结构 | `uv run python -c "import PIL"` 成功 |
| S2 | 建 SQLite DB ✅ | `tnjindex.db` + 建表脚本 | `.schema` 输出与 §1 字段完全一致 |
| S3 | 通用 ingest | `ingest.py`：规范化 → 缩略图 → 去重 → 写 DB | 5 张测试图入库；重复图被跳过 |
| S4 | KYM 爬虫 | `kym.py`：爬分页 + 下载 + 触发 ingest | DB ≥ 200 条，无重复 |
| S5 | 补量入库 | 手动收集图片走 ingest.py | DB 总记录 ≥ 500，全部 `annotation_status = raw` |

---

## S1 · 项目初始化

**目标**: 建立可复现的 Python 开发环境与目录骨架。

**任务**:
- [x] `uv init` 初始化项目，生成 `pyproject.toml`
- [x] 添加依赖：`requests`、`beautifulsoup4`、`Pillow`、`imagehash`
- [x] 按 §2 创建目录结构：
  ```
  data/images/originals/
  data/images/thumbnails/
  data/db/
  scrapers/
  pipelines/
  ```
- [x] 添加 `.gitignore`（忽略 `data/`、`.venv/`、`*.db`）

**验收**:
- [x] `uv run python -c "import PIL, imagehash, bs4"` 无报错
- [x] 目录结构与 §2 一致

---

## S2 · 建 SQLite DB

**目标**: 按 §1 Schema 建表，提供初始化脚本，支持幂等重建。

**任务**:
- [x] 编写 `scrapers/db.py`：封装连接、建表、基础 CRUD
- [x] `items` 表字段：`id`、`title`、`image_path`、`thumbnail_path`、`tags`（JSON）、`description`、`source_note`、`annotation_status`、`phash`、`created_at`
- [x] `annotation_status` 约束：只允许 `raw` / `annotated`
- [x] 建表逻辑使用 `CREATE TABLE IF NOT EXISTS`（幂等）

**验收**:
- [x] 运行 `uv run python scrapers/db.py`（或 `init` 命令）后 `tnjindex.db` 出现
- [x] `sqlite3 data/db/tnjindex.db ".schema items"` 输出与 §1 字段完全一致

---

## S3 · 通用 ingest

**目标**: 实现核心入库管线，手动图片与爬虫图片均走此路径。

**任务**:
- [ ] 编写 `scrapers/ingest.py`，暴露 `ingest_image(src_path, source_note=None)` 函数，按序执行：
  1. **规范化文件名**：重命名为 `image_XXXXX.jpg`（5 位零填充序号），复制至 `data/images/originals/`
  2. **生成缩略图**：长边 400px，保持比例，JPEG Q75，存入 `data/images/thumbnails/`
  3. **pHash 去重**：计算感知哈希，与 DB 内已有哈希对比，汉明距离 ≤ 8 则跳过并日志提示
  4. **写 DB**：插入 `items` 记录，`title = ""`，`tags = []`，`annotation_status = raw`
- [ ] pHash 值存入 DB（需在 `items` 表加 `phash` 字段，或维护内存集合——**建议加字段，方便后续查询**）

> `phash` 已写入 `tech_design.md` §1；S3 实现 ingest 时写入该列。

**验收**:
- [ ] 手动放 5 张图（含 1 张与已入库图相似的）至临时目录，批量调用 `ingest_image`
- [ ] DB 中出现 4 条记录（重复图被跳过，日志输出 `[SKIP] duplicate: ...`）
- [ ] `data/images/thumbnails/` 中缩略图长边 ≤ 400px

---

## S4 · KYM 爬虫

**目标**: 爬取 KYM Tom & Jerry 图库全量图片（~252 张），自动入库。

**任务**:
- [ ] 编写 `scrapers/kym.py`：
  - 爬取分页：`https://knowyourmeme.com/memes/tom-and-jerry/photos?page=N`
  - 解析每页图片直链（`<img>` 或 `<a>` 标签）
  - 下载原图至临时目录，调用 `ingest_image(path, source_note=kym_url)`
  - 支持 `--dry-run`（只爬不下载）与 `--limit N` 参数
- [ ] 添加基本礼貌：`time.sleep(1~2s)` 请求间隔、`User-Agent` header
- [ ] 断点续跑：已在 DB 中的 `source_note` URL 跳过重新下载

**验收**:
- [ ] `uv run python scrapers/kym.py --dry-run` 输出解析到的图片数量（应 ≈ 252）
- [ ] 正式运行完成后 `SELECT COUNT(*) FROM items` ≥ 200
- [ ] 无重复记录（pHash 去重生效）

---

## S5 · 补量入库（手动收集）

**目标**: 通过手动收集国内社区梗图，将总量补至 ≥ 500 条。

**背景**: 优先收「迷之契合」语境的梗图（B 站评论区截图、小红书、贴吧等），补充 KYM 覆盖不足的中文语境素材。

**任务**:
- [ ] 手动收集约 250 张图片，存入本地临时目录
- [ ] 批量调用：`uv run python scrapers/ingest.py --dir <临时目录>`（需支持目录批量模式）
- [ ] 为 `ingest.py` 添加 `--dir` 参数，遍历目录下所有 `.jpg/.png/.webp` 文件

**验收**:
- [ ] `SELECT COUNT(*) FROM items WHERE annotation_status = 'raw'` ≥ 500
- [ ] `SELECT COUNT(*) FROM items WHERE thumbnail_path IS NOT NULL` = 总记录数（所有图均有缩略图）
- [ ] 抽查 10 条记录，`image_path` 与 `thumbnail_path` 文件均实际存在

---

## 技术说明

- **依赖包**: `requests`、`beautifulsoup4`、`Pillow`、`imagehash`
- **模型变更**: `phash` 已纳入 `tech_design.md` §1 与 `items` 表
- **影响模块**: `scrapers/db.py`、`scrapers/ingest.py`、`scrapers/kym.py`
- **注意事项**: `data/` 目录不入 Git；`tnjindex.db` 不入 Git

## 不在范围

- AI 标注（`title`/`tags`/`description` 字段留空）→ Phase 02
- 向量索引构建 → Phase 02
- Imgflip 爬虫扩量 → Phase 01 完成后按需
- 视频帧提取 → 暂不在路线图内
