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
| `source_note` | string | Y | 来源备注（如视频文件名、社区链接等），可为空 |
| `annotation_status` | enum | N | `raw`（未标注）/ `annotated`（已完成 AI 标注）；用于 Phase 02 增量处理 |
| `phash` | string | Y | 感知哈希（pHash，64-bit hex），用于入库时去重；汉明距离 ≤ 8 视为重复图片 |
| `created_at` | timestamp | N | 入库时间 |

> **embedding 向量**不在此表存储，存储方案见 §4 检索架构。

### 约束

- `tags` 逻辑类型为 `string[]`，物理存储格式见 §2/§4（SQLite JSON 列、PG array 列、或向量 DB metadata）。
- `title` 仅含小写英文、数字、下划线，长度上限 80 字符；AI 生成时在 prompt 中约束格式。
- `description` 长度上限 500 字符（AI 生成时在 prompt 中约束）。
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

> Phase 03 前迁移：`originals/` + `thumbnails/` 上传对象存储（R2/OSS），`image_path` / `thumbnail_path` 更新为公开 URL；DB 按 §4/§5 选型迁移或保留。

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

将 `annotation_status = raw` 的 Item 批量处理，一次 Vision API 调用同时输出 `title`、`tags`、`description` 三个字段，写回 DB 并更新状态为 `annotated`。

### Vision 模型选型

**待实测确定**，候选：`gpt-4o`（OpenAI）和 `qwen-vl-max`（阿里云 DashScope）。

选型流程：
1. 取 10～20 张典型梗图，两个模型各跑一遍相同 prompt
2. 人工对比：标注一致性、`tags` 的准确度、`description` 的语感
3. 记录实测 token 用量，按当时价目表估算 500 张总费用
4. 择优写入本节，另一个进 `<details>` 存档

> 两者均支持 JSON mode（结构化输出），切换成本低，代码层用接口抽象隔离，换模型不改业务逻辑。

### 单次调用 Prompt 设计（草稿）

```
你是一个《猫和老鼠》梗图标注专家。分析这张图片，用 JSON 返回以下字段：

{
  "title": "snake_case 短标题，描述画面核心内容，同时适合作为文件名，仅含小写英文/数字/下划线，≤ 80 字符",
  "tags": ["3～8 个简短标签，覆盖：角色、情绪/氛围、画面动作、可用于的社区语境"],
  "description": "1～3 句话，描述画面内容与氛围，以及这张图「迷之契合」什么类型的讨论语境，≤ 500 字符"
}

只返回 JSON，不要其他内容。
```

> Prompt 在实测阶段迭代，最终版本与模型一起写入本节。

### 处理管线

```
DB 查询 annotation_status = raw 的 Item
    │
    ▼
[1] 读取 thumbnail（节省 token）
    │
    ▼
[2] Vision API 调用（JSON mode）
    │
    ├─ 成功 → 写回 title / tags / description，status = annotated
    │
    └─ 失败 → 记录 error_log，status 保持 raw，支持重试
    │
    ▼
[3] 批量完成后，输出统计：成功 N 条 / 失败 M 条 / 预估费用
```

**注**：调用 thumbnail 而非原图，在大多数 Vision 模型中可显著降低 image token 用量，对梗图内容识别影响极小。

### 脚本

- `pipelines/annotate.py`：读取 raw items → 调 Vision API → 写回 DB，支持 `--limit N` 增量运行与断点续跑。

<details>
<summary>候选方案对比（模型待实测确定）</summary>

**GPT-4o（OpenAI）**
- 优点：中英文理解强，JSON mode 稳定，生态文档丰富
- 缺点：需境外网络/代理；价格以官网为准，需实测

**Qwen-VL-Max（阿里云 DashScope）**
- 优点：国内访问无障碍，中文语感好，有免费额度
- 缺点：对《猫和老鼠》英文梗图的英文 tag 质量待验证

**一次调用 vs 分步调用**
- 分步（先 description → 再提取 tags）质量略高，但 token 消耗翻倍
- **一次调用（已选）**：500 条规模下质量差异可接受，成本更低

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

### Embedding 模型

与 Vision 模型同策略——**待实测确定**，候选：

| 模型 | 维度 | 特点 |
|------|------|------|
| `text-embedding-3-small`（OpenAI） | 1536 | 英文质量高，价格极低（约 $0.02/1M tokens） |
| `text-embedding-v3`（阿里 DashScope） | 1024 | 中文友好，国内访问无障碍 |

> 因为 `description` 和 `tags` 以中英文混合为主，两者效果差异不大；建议与 §3 Vision 模型保同一厂商，减少 API Key 管理成本。

**被 embed 的内容**：将 `description` + `tags`（join 为空格分隔字符串）拼接后 embed，作为每条 Item 的语义向量。

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

**前后端分离**：Python FastAPI 后端 + 静态前端，各自独立部署。

```
用户浏览器
    │
    ├─ 静态资源（HTML/JS/CSS）← Vercel（免费）
    │
    └─ API 请求 → FastAPI（Fly.io 免费额度）
                        │
                        ├─ SQLite + sqlite-vec（持久化磁盘）
                        │
                        └─ 图片 URL 指向 Cloudflare R2（免费额度 10 GB）
```

选型理由：
- Phase 01～02 已是 Python；FastAPI 直接复用 sqlite-vec 查询逻辑，无需跨语言桥接
- 前端无 SEO 强需求（工具站），纯静态够用，无需 SSR
- **总云成本趋近于零**：Fly.io 免费 3 VM / Vercel 免费 / R2 免费 10 GB

### 技术栈

| 层 | 选型 | 说明 |
|----|------|------|
| 后端 API | FastAPI（Python） | 复用 Phase 01～02 代码；`/search`、`/items/{id}` 等端点 |
| 前端 | React（Vite）| 轻量，无 SSR；与后端完全解耦 |
| 图片存储 | Cloudflare R2 | Phase 03 前从本地迁入；`image_path` / `thumbnail_path` 更新为 R2 公开 URL |
| 后端部署 | Fly.io | 含持久化磁盘（挂载 SQLite 文件） |
| 前端部署 | Vercel | 静态托管，自动 CI/CD |

### API 端点（MVP 最小集）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/search` | GET | `?q=自然语言&tags=tag1,tag2&limit=20`；返回 Item 列表（含 thumbnail_url） |
| `/items/{id}` | GET | 返回单条 Item 详情（含 image_url、tags、description） |
| `/tags` | GET | 返回全量标签列表，用于 UC-03 标签筛选面板 |

### 部署流程

```
代码推送 main 分支
    │
    ├─ GitHub Actions → Fly.io 部署后端
    │
    └─ Vercel 自动检测 → 部署前端静态资源
```

<details>
<summary>候选方案对比（已决策）</summary>

**Next.js 全栈（SSR）vs FastAPI + 静态前端（已选）**
- Next.js：前后端一套代码，Vercel 零配置部署，但 API routes 为 Node.js，调用 Python sqlite-vec 需要额外进程通信或放弃 sqlite-vec
- **FastAPI + 静态前端（已选）**：后端直接复用 Phase 01～02 Python 代码，sqlite-vec 无缝集成；前端静态部署成本更低；对后端倾向的开发者更顺手

**托管：Fly.io vs Railway vs VPS**
- Railway：易用，但免费额度 2026 年后收紧
- VPS（如 DigitalOcean）：灵活，但需手动运维
- **Fly.io（已选）**：免费额度含持久化磁盘，SQLite 文件可直接挂载，适合个人项目

**图片存储：Cloudflare R2 vs 阿里云 OSS**
- 阿里云 OSS：国内访问快，但免费额度少
- **R2（已选）**：免费 10 GB + 免费出口流量（无 egress 费用），对个人项目几乎零成本

</details>