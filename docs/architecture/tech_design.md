# 技术设计

## 1. 数据模型（Item Schema）

**素材（Item）** 是系统内最小可检索、可展示单位。每条 Item 对应一张《猫和老鼠》相关截图/梗图及其元数据。

### 字段定义

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | integer (auto-increment) | N | 主键 |
| `title` | string | N | snake_case 短标题，简述画面内容（如 `tom_pretending_to_be_dead`）；同时作为图片下载文件名；Phase 02 由 AI 填写，入库时先填空串占位 |
| `image_path` | string | N | 原图存储路径（本地路径或对象存储 URL，具体见 §2） |
| `thumbnail_path` | string | Y | 缩略图路径，用于网站列表展示；Phase 01 入库时生成，与原图同目录或同 bucket |
| `tags` | string[] | N | 扁平标签列表，默认空数组；Phase 02 由 AI 填写 |
| `description` | string | Y | 自然语言描述画面内容与氛围；Phase 02 由 AI 填写 |
| `composition` | string | Y | 构图/镜头/主体位置与视觉重心的短摘要（≤200 字）；**S1-v3** 起由 AI 填写；未重跑前可为空 |
| `source_note` | string | Y | 来源备注（如视频文件名、社区链接等），可为空 |
| `annotation_status` | enum | N | `raw`（未标注）/ `annotated`（已完成 AI 标注）；用于 Phase 02 增量处理 |
| `phash` | string | Y | 感知哈希（pHash，64-bit hex），用于入库时去重；汉明距离 ≤ 8 视为重复图片 |
| `created_at` | timestamp | N | 入库时间 |

> **embedding 向量**不在此表存储，存储方案见 §4 检索架构。

### 约束

- `tags` 逻辑类型为 `string[]`，物理存储格式见 §2/§4（SQLite JSON 列、PG array 列、或向量 DB metadata）。
- `title` 仅含小写英文、数字、下划线，长度上限 80 字符；AI 生成时在 prompt 中约束格式。
- `description` 长度上限 500 字符（AI 生成时在 prompt 中约束）。
- `composition` 长度上限 200 字符（校验见 `pipelines/annotation_validate.py`）；已标注条目应为非空字符串。
- `thumbnail_path` 可为空：入库时若尚未生成缩略图，前端降级展示原图。
- `image_path` 在 Phase 01 阶段允许为本地相对路径；迁移至对象存储后原地更新，不变更其他字段。
- `phash` 在入库时计算并存储；Phase 01 新增，§1 原始草稿未包含此字段。

<details>
<summary>候选方案对比（已决策）</summary>

**A. 标签分层（theme + tags） vs 扁平 tags**
- 分层：`theme`（宏观话题）+ `tags[]`（细粒度），查询更丰富，但 AI 标注需额外约定主题词表，复杂度高。
- **扁平（已选）**：单一 `tags[]`，主题可作为普通标签处理，MVP 够用；后续有需要可加 `theme` 字段迁移。

**B. 结构化来源（episode + timestamp）vs source_note 可空**
- 结构化：支持精确定位到集数/时间码，但手工或自动补全成本高，且梗图来源常不可溯。
- **source_note 可空（已选）**：仅记录能拿到的备注，不强制格式。

</details>

## 2. 数据采集方案

### 数据源策略

多源组合，优先拿质量最高的种子数据，再扩量：

| 来源 | 估计规模 | 获取方式 | 优先级 |
|------|---------|---------|--------|
| [Know Your Meme · Tom and Jerry 图库](https://knowyourmeme.com/memes/tom-and-jerry/photos) | ~252 张 | HTML 分页爬虫（无官方 API）| P0 · 种子数据 |
| 国内社区手动收集（B站、小红书、贴吧） | 按需补充 | 手动截图/下载，重点收「迷之契合」语境的梗图 | P0 · 补充语境质量 |
| Imgflip Tom & Jerry tag | 数千张（用户创作） | 爬虫；需去重与质量过滤（大量重复模板加文字）| P1 · 扩量用 |

> KYM 种子数据约 252 张 + 手动补充约 250 张 = 目标 500 条可达。Imgflip 扩量留待后续。

**不在范围**：视频帧批量提取（「哪帧有梗」的筛选问题暂无低成本解法）；Tenor/GIPHY API（以 GIF 为主，且 Tenor 已停止新接入）。

---

### 入库流程

```
原始图片（下载/手动）
    │
    ▼
[1] 规范化文件名        image_xxxxx.jpg（临时名，title 由 Phase 02 AI 填写）
    │
    ▼
[2] 生成缩略图          resize → 长边 400px，保持比例，JPEG Q75
    │
    ▼
[3] 写入 DB            插入 Item 记录，annotation_status = raw
    │
    ▼
[4] 去重检查            基于感知哈希（pHash）跳过重复图片；汉明距离 ≤ 8 视为重复
```

### 本地目录结构（Phase 01～02）

```
data/
├── images/
│   ├── originals/     # 原图
│   └── thumbnails/    # 缩略图（与原图同文件名）
└── db/
    └── tnjindex.db    # SQLite（Phase 01～02 本地开发用）
```

> Phase 03 已完成迁移：`originals/` + `thumbnails/` 已上传阿里云 OSS 香港；`image_path` / `thumbnail_path` 为公开 URL（脚本见 `pipelines/migrate_to_oss.py`）。本地 `data/images/` 可保留作备份；DB 仍用 SQLite，与 §4 一致。

### 采集脚本职责（Phase 01 实现）

- `scrapers/kym.py`：爬取 KYM Tom & Jerry 图库分页，下载原图，触发入库流程。
- `scrapers/ingest.py`：通用入库逻辑（规范化 → 生成缩略图 → 去重 → 写 DB），手动收集的图片也走此脚本。

<details>
<summary>候选方案对比（已决策）</summary>

**数据源：视频帧提取 vs 社区爬取 + 手动收集**
- 视频帧提取：完整覆盖剧集，但 99% 的帧不是梗图；「挑出有趣帧」本身是难题，成本高。
- **社区爬取 + 手动（已选）**：KYM 已是社区验证的梗图库；国内手动收集补「迷之契合」语境；两者合计可达 500 条目标。

**图像存储：本地 vs 对象存储**
- 对象存储（R2/OSS）是最终形态，但 Phase 01～02 无需公网访问，本地开发更快。
- **本地先行（已选）**：`image_path` 字段设计支持原地替换为 URL，迁移成本低。

</details>

## 3. AI 标注与处理管线

### 目标

将 `annotation_status = raw` 的 Item 批量处理，一次 Vision API 调用同时输出 `title`、`tags`、`description`、`composition` 四个字段，写回 DB 并更新状态为 `annotated`。

### Vision 模型选型（S2-v2 更新，2026-04-12；S1-v3 仅增输出字段 2026-04-14）

**默认**：OpenAI **`gpt-4o`**（`TNJ_VISION_PROVIDER` 未设置或为 `openai`；可用 `TNJ_VISION_MODEL` 覆盖具体型号）。

**主力（生产用）**：阿里云 DashScope（设置 `TNJ_VISION_PROVIDER=dashscope`，密钥 `DASHSCOPE_API_KEY`）；代码默认多模态型号 **`qwen3.6-plus`**（2026-04-12 升级，原为 `qwen3.5-flash`），可用 `TNJ_VISION_MODEL` 覆盖。

实现与仓库内 [`pipelines/vision_client.py`](pipelines/vision_client.py) 对齐；小样本对比可运行：

- `uv run python -m pipelines.vision_eval --limit 20 --provider openai`
- `uv run python -m pipelines.vision_eval --limit 20 --provider dashscope`

> 两者均支持 JSON 结构化输出；切换只改环境变量，业务逻辑不变。全库跑批前仍建议用 10 张图做一次人工对比。

### Prompt 设计（S1-v3，2026-04-14；在 S2-v2 骨架上增加 `composition`）

> **S2-v2（2026-04-12）**：目视验收发现原 prompt 输出「梗图解说体」、向量与画面脱节；修订为**只描述可见客观内容 + 折叠搜索短句**。  
> **S1-v3（2026-04-14）**：为构图检索增加必填 **`composition`**（≤200 字，镜头/主体相对位置/视觉重心），与 `title`/`tags`/`description` 同次 JSON 输出。全文以仓库 [`pipelines/prompts.py`](../pipelines/prompts.py) 中 `VISION_ANNOTATION_PROMPT` 为准，此处不重复粘贴，避免与代码漂移。

JSON 字段概要：`title`、`tags`、`description`（约束同 S2-v2）、**`composition`**（非空、≤200 字）。

### 处理管线

```
DB 查询 annotation_status = raw（或 --force 时含 annotated）的 Item
    │
    ▼
[1] 解析图像输入（`pick_image_for_vision`：本机缩略图/原图优先，否则 OSS `https://` URL）
    │
    ▼
[2] Vision API 调用（JSON mode）—— 实时 或 Batch File API
    │
    ├─ 成功 → 写回 title / tags / description / composition，status = annotated
    │
    └─ 失败 → stderr 日志记录原因，status 保持 raw，支持重试
    │
    ▼
[3] 批量完成后，输出统计：成功 N 条 / 失败 M 条
```

**注**：调用 thumbnail 而非原图，在大多数 Vision 模型中可显著降低 image token 用量，对梗图内容识别影响极小。

### 脚本

- `pipelines/annotate.py`：读取 items → 调 Vision API → 写回 DB；`--limit N`、`--dry-run`、`--force`（含已 `annotated` 条目）、`--enable-batch`（Batch File API 模式）。`pipelines.paths.pick_image_for_vision`：优先本机 `data/images/...`，否则直接使用 DB 中的公网 `https://` 缩略图/原图 URL（由模型侧拉取，不落盘）。
- `pipelines/batch_utils.py`：DashScope Batch File API 封装（上传 JSONL、提交任务、轮询、解析写库）；费率约实时 50%，`enable_thinking=false` 已内置。
- `pipelines/vision_eval.py`：不写库，对样本输出 JSONL 便于对比模型。
- `pipelines/vec_smoke.py`：sqlite-vec + `item_embeddings` 最小写入与 MATCH 冒烟（M1）。

<details>
<summary>候选方案对比（归档）</summary>

**GPT-4o（OpenAI）**
- 优点：中英文理解强，JSON mode 稳定，生态文档丰富
- 缺点：需境外网络/代理；价格以官网为准，需实测

**DashScope 多模态（当前默认 `qwen3.6-plus`；历史对比过 `qwen3.5-flash`、`qwen-vl-max`）**
- 优点：国内访问无障碍，中文语感好，支持 Batch File API（50% 折扣）
- 缺点：`qwen3.6-plus` 等 Plus 系列默认开启思考模式，Batch 请求中需显式 `enable_thinking=false`

**一次调用 vs 分步调用**
- 分步（先 description → 再提取 tags）质量略高，但 token 消耗翻倍
- **一次调用（已选）**：500 条规模下质量差异可接受，成本更低

**实时调用 vs Batch File API**
- 实时：逐条返回，便于即时验收；适合小批量测试
- **Batch（可选）**：全量重标注时约 50% 费用，异步轮询；`--enable-batch` 参数启用

</details>

## 4. 检索架构

### 整体方案

两条检索路径，最终合并结果：

```
用户输入
    │
    ├─ 自然语言查询（UC-01）
    │       │
    │       ▼
    │   Embedding 模型 → query vector
    │       │
    │       ▼
    │   sqlite-vec 近似最近邻（ANN）→ Top-K 候选
    │
    └─ 标签筛选（UC-03）
            │
            ▼
        SQLite JSON 字段过滤（WHERE tags LIKE / JSON_EACH）

两路可独立触发，也可组合：先标签过滤缩小候选集，再在候选集内做向量检索。
```

### 向量存储：sqlite-vec

- Phase 01～02：向量存在同一 `tnjindex.db` 的 `item_embeddings` 虚拟表（sqlite-vec 扩展）
- 500 条规模下 ANN 延迟 < 10ms，无需额外服务
- Phase 03 上线后，视实际并发与规模决定是否迁移至托管向量服务（Pinecone / Weaviate Cloud 等）；迁移不影响 §1 数据模型

### Embedding 模型（M3 定稿）

本仓库 Phase 02 **默认选型**（与 `pipelines/constants.py` 中 `EMBEDDING_DIM=1536` 及 `pipelines/embed_client.py` 一致；可用 `TNJ_EMBED_*` 覆盖）：

| 场景 | 模型 | 维度 | 说明 |
|------|------|------|------|
| **默认（OpenAI）** | `text-embedding-3-small` | 1536 | 与 Vision 同厂商时 Key 管理简单；M3 全量 embed 已按此维度写入 `item_embeddings` |
| **备选（DashScope）** | `text-embedding-v4`（代码默认） | 1536 | 与表宽对齐；国内网络友好 |

历史候选（未作为本仓库默认表宽）：`text-embedding-v3`（DashScope，最高 1024 维）等——若改用非 1536 维模型，须同步改 `EMBEDDING_DIM` 并 **`embed.py --force` 重建** `item_embeddings`。

> 因为 `description` 和 `tags` 以中英文混合为主，OpenAI 与 DashScope 在 500 条量级下可择一为主；建议与 §3 Vision 模型尽量同厂商，减少 API Key 管理成本。

**被 embed 的内容**（**S1-v3** 起，与 [`pipelines/embed.py`](../pipelines/embed.py) 一致）：将每条 Item 上**非空**的 `description`、`composition`、以及 `tags`（JSON 数组 join 为空格分隔字符串）按此顺序用空格拼接后 embed，作为语义向量。

### 检索流程（Phase 02：CLI + 本地测试页验证）

```python
# 伪代码
query_vec = embed(user_query)
results = db.execute("""
    SELECT i.*, vec_distance_cosine(e.embedding, ?) AS score
    FROM item_embeddings e
    JOIN items i ON i.id = e.item_id
    ORDER BY score ASC
    LIMIT 10
""", [query_vec])
```

Phase 02 交付标准：以**同一检索逻辑**提供 **CLI** 与 **本地极简测试页**；输入自由文本返回 Top-K（如 10）；测试页须**展示对应缩略图/原图**以便主观与数据对照；固定查询集（10～20 条）人工抽检 Top-5 相关性通过（细则见 `docs/mvp/02_annotation_index.md`）。

**实现注记**：`pipelines/search.py` 使用 sqlite-vec `vec0` 的 `WHERE embedding MATCH ? AND k = ?` 做 KNN，再按命中顺序回查 `items`；与上文「`JOIN` + `vec_distance_cosine`」伪代码等价目标（Top-K 语义近邻）、具体 SQL 以代码为准；`vec0` 距离度量以建表时配置为准（未显式指定时为扩展默认）。

### 结构化标签过滤（Phase 03）

SQLite 的 `JSON_EACH` 支持对 `tags` 数组做精确过滤，500 条规模下全表扫描即可，无需额外索引。

```sql
SELECT * FROM items
WHERE EXISTS (
    SELECT 1 FROM JSON_EACH(items.tags) WHERE value = '目标标签'
)
```

<details>
<summary>候选方案对比（已决策）</summary>

**本地（sqlite-vec / Chroma）vs 托管（Pinecone / Weaviate Cloud）**
- 托管服务：开箱即用，支持高并发，但有网络延迟与费用，本地开发调试复杂
- **sqlite-vec（已选）**：零运维，与业务 DB 同文件，500 条规模完全够用；Phase 03 上线若有性能瓶颈再迁移，迁移路径清晰

**embed 内容：仅 description vs description + tags 拼接**
- 仅 description：语义更纯，但丢失标签信息
- **description + tags 拼接（已选）**：tags 本质是关键词，拼入 embed 内容可增强召回

</details>

## 5. 网站架构

### 整体架构

**FastAPI 一体化部署**：后端同时提供 API 与前端静态资源，统一部署于 Fly.io **新加坡 `sin` 区域**（Fly 已不再提供香港 `hkg` Machines）；图片存储仍于阿里云 OSS 香港节点。

```
用户浏览器（主要：中国大陆）
    │
    └─ 所有请求 → FastAPI（Fly.io `sin` 节点；HTML/API RTT 因大陆出口线路而异，通常几十～百余 ms 量级）
                        │
                        ├─ /api/* → 业务 API 端点
                        │       └─ SQLite + sqlite-vec（persistent volume）
                        │
                        ├─ /*    → React 静态产物（StaticFiles mount）
                        │
                        └─ 图片 URL 指向阿里云 OSS 香港节点
```

选型理由：
- Phase 01～02 已是 Python；FastAPI 直接复用 sqlite-vec 查询逻辑，无需跨语言桥接
- 前端无 SEO 强需求（工具站），纯静态够用，无需 SSR
- **前后端合并部署**：消除 Vercel（大陆访问不稳定）；HTML/API 走单一 Fly 区域（`sin`），体验一致
- **图片存储换 OSS HK**：阿里云 OSS 香港节点大陆直连延迟低；R2 无 CDN 大陆直连慢

### 技术栈

| 层 | 选型 | 说明 |
|----|------|------|
| 后端 API | FastAPI（Python） | 复用 Phase 01～02 代码；所有端点统一加 `/api` 前缀 |
| 前端 | React（Vite）| `build.outDir` 指向 `backend/static/`；由 FastAPI `StaticFiles` serve |
| 图片存储 | 阿里云 OSS 香港节点 | Phase 03 已从本地迁入；`image_path` / `thumbnail_path` 为 OSS 公开 URL |
| 部署 | Fly.io `sin` region | 含 persistent volume（挂载 SQLite 文件）；Fly 已不再提供 `hkg`，与 volume 同区部署 |
| CI/CD | GitHub Actions → Fly.io | 前端 build + `flyctl deploy --remote-only`；统一单流水线 |

### API 端点（MVP 最小集）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/search` | GET | `?q=自然语言&tags=tag1,tag2&limit=20&offset=0`；返回 Item 列表（含 thumbnail_url） |
| `/api/items/{id}` | GET | 返回单条 Item 详情（含 image_url、tags、description、composition） |
| `/api/tags` | GET | 返回全量标签列表（按出现频次排序），用于 UC-03 标签筛选面板 |

### 部署流程

```
代码推送 main 分支
    │
    └─ GitHub Actions
            │
            ├─ npm ci && npm run build    ← 前端构建，产物输出至 backend/static/
            │
            └─ flyctl deploy --remote-only ← 打包镜像（含前端产物）并部署至 Fly.io `sin`
```

<details>
<summary>候选方案对比（已决策）</summary>

**Next.js 全栈（SSR）vs FastAPI + 静态前端（已选）**
- Next.js：前后端一套代码，Vercel 零配置部署，但 API routes 为 Node.js，调用 Python sqlite-vec 需要额外进程通信或放弃 sqlite-vec
- **FastAPI + 静态前端（已选）**：后端直接复用 Phase 01～02 Python 代码，sqlite-vec 无缝集成；前端合并部署，无额外托管依赖

**前端托管：Vercel vs FastAPI StaticFiles（已选）**
- Vercel：CI/CD 便捷，但大陆访问不稳定，且需维护双平台
- **FastAPI StaticFiles（已选）**：前后端同域同节点，无跨域问题；部署流水线统一；大陆访问体验取决于 Fly.io 所选区域（当前 `sin`），与 API 一致

**托管：Fly.io `sin` vs Railway vs VPS**
- Railway：易用，但免费额度 2026 年后收紧；区域与定价以官方为准
- VPS（如阿里云香港 ECS）：灵活可控，但需手动运维 nginx / SSL / 更新
- **Fly.io `sin`（已选）**：免费额度含 persistent volume，SQLite 直接挂载；Fly 已不再提供 `hkg` Machines，故采用新加坡；自动 TLS；适合个人项目

**图片存储：Cloudflare R2 vs 阿里云 OSS 香港（已选）**
- Cloudflare R2：免费 10 GB + 无 egress 费用，但无 CDN（R2 公开访问走 Cloudflare 边缘，大陆不稳定）
- **阿里云 OSS 香港（已选）**：大陆直连延迟低（30-50ms）；开发者已有阿里云账号；500 张图成本约 ¥0.12/GB/月，几乎忽略不计

</details>