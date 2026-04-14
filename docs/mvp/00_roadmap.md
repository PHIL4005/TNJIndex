# 路线图（Roadmap）

> 本文档是 TNJIndex 的**阶段总览**，记录每个 Phase 的目标、状态与前置依赖。  
> 各 Phase 细节见对应子文件；技术选型与架构决策见 [`architecture/tech_design.md`](../architecture/tech_design.md)。

将《猫和老鼠》里「和讨论语境迷之契合」的截图/梗图，从「刷到算赚到」变成「按意图查找」。  
→ 背景与动机详见 [`intro_to_tnjinex.md`](../intro_to_tnjinex.md)

---

## 核心用例

MVP 交付物是一个**可公开访问的网站**，满足以下用例：

| UC | 名称 | 用户能做什么 | 优先级 |
|----|------|------------|--------|
| UC-01 | 自然语言搜索 | 输入自由文本描述想要的氛围/情绪（如「用力过猛但又翻车」），系统返回相关截图列表 | P0 |
| UC-02 | 素材详情 | 点击截图查看大图 + 标签 + 描述文本 | P0 |
| UC-03 | 标签筛选 | 从标签列表点选，过滤并浏览相关素材 | P1 |
| UC-04 | 素材复用 | 一键复制图片链接，方便直接粘贴到社区帖子 | P1 |
| UC-05 | 以图搜图 | 上传一张参考图，系统返回构图/视觉结构相似的猫鼠截图 | P1 |

---

## Phase 总览

| # | 名称 | 状态 | 核心目标 | 前置依赖 |
|---|------|------|---------|---------|
| 01 | 数据基础 | ✅ 已完成 | 定义 Item Schema，跑通采集 → 入库链路 | `tech_design §1 §2` 定稿 |
| 02 | AI 标注与索引 | ✅ 已完成（M1–M3：全量标注/embed、固定查询抽检、文档关门） | 图像 → 可检索元数据；建立搜索索引 | Phase 01 ✅ + `tech_design §3 §4` 定稿 |
| 03 | 产品设计 | ✅ 已完成 | 锁定网站架构与交互方案，产出可直接开发的设计 | Phase 02 检索验收通过（CLI + 本地测试页）+ `tech_design §5` 定稿 + OSS 迁移 |
| 04 | MVP 开发与上线 | ✅ P0 已完成（S1–S4；Fly `sin` + Actions，2026-04-12） | 实现核心用例，部署为公开可访问的网站 | Phase 03 完成 |
| 05 | UX 改版 · 搜索优化 · 以图搜图 | 🔄 进行中 | 构图标注升级 + 重 embed；CLIP 以图搜图（UC-05）；视觉改版 | Phase 04 ✅ |

---

## Phase 说明

### Phase 01 · 数据基础

> 详细文档：[`01_data_foundation.md`](01_data_foundation.md)  
> ✅ **已完成**：`tech_design §1` / `§2` 定稿；本地库 ≥500 条规范化 Item；采集与 ingest 管线已验收（见子文档）。

**目标**：先锁定「一条 Item 长什么样」，再开始批量采集——避免数据积累后因 Schema 不合适而推倒重来。

**关键决策**（在 `tech_design §1 §2` 中确定）：
- 数据源：视频文件直接提取帧 vs 从社区爬取现有图片？
- 图像存储：本地文件系统 / 对象存储？
- 元数据存储：选哪种 DB？最小字段集是什么（保证 Phase 02 能用）？

**交付**：本地库中有 ≥ 500 条规范化 Item；采集脚本可复用跑完全量。

**学习点**：数据采集技术（帧提取 / 爬虫）、DB Schema 设计、批量 ETL。

---

### Phase 02 · AI 标注与索引

> 详细文档：[`02_annotation_index.md`](02_annotation_index.md)  
> ✅ **已完成**：Phase 01 完成；`tech_design` §3 / §4 定稿；全量标注 + 向量索引；固定查询集与抽检见 `pipelines/eval_queries.txt`、`pipelines/eval_memo.md`。  
> **S2-v2（2026-04-12）**：prompt 与 DashScope 模型升级、OSS URL 标注路径、Batch 可选；全量重标 + 重 embed 后复检已记入 `eval_memo.md`。

**目标**：跑通「原始图像 → 标签/描述/向量 → 可搜索索引」全管线；在 **CLI + 本地极简测试页** 上验证语义检索质量（测试页须**展示检索到的图片**），再进入 Phase 03。

**关键决策**（在 `tech_design §3 §4` 中确定）：
- Vision 模型选型（成本 × 质量权衡）；prompt 设计保证标注一致性
- Embedding 模型与维度
- 向量检索方案：本地（sqlite-vec / Chroma 等）vs 云托管
- 结构化字段索引策略（UC-03 标签筛选实现放在 Phase 03/04，本 Phase 不交付）

**交付**：全量 Item 完成 AI 标注与向量索引；本地可通过自然语言得到 Top-K；**固定查询集抽检**在带图测试页上完成，并与 CLI 结果一致。

**学习点**：Vision API 与 prompt 工程、embedding、向量数据库、AI 调用成本控制。

---

### Phase 03 · 产品设计

> 详细文档：[`03_product_design.md`](03_product_design.md)  
> ✅ **已完成**：`tech_design §5` 定稿（Fly.io `sin` + FastAPI serve 前端 + 阿里云 OSS HK）；S1–S5 与 `03_product_design.md` 验收已勾选；S2 图片已迁移至 OSS HK，`pipelines/migrate_to_oss.py` 与本地测试页验证通过。

**目标**：Phase 04 开始写代码前，把「做什么」和「怎么做」都锁定——避免边写边推翻框架选型。

**关键决策**（在 `tech_design §5` 中确定）：
- 前后端架构：SSR 全栈框架（如 Next.js）vs 前后端分离？
- API 层：检索服务如何暴露（REST / tRPC / 直接调用）？
- 托管与部署：Vercel / Fly.io / Railway 等，如何做持续部署？

**设计产出**（在 `03_product_design.md` 中记录）：

| 用例 | 设计内容 |
|------|---------|
| UC-01 自然语言搜索 | 搜索框交互、结果卡片布局、空状态与加载态 |
| UC-02 素材详情 | 详情页/浮层结构、大图 + 标签 + 描述排布 |
| UC-03 标签筛选 | 标签列表呈现方式、多选交互 |
| UC-04 素材复用 | 复制链接按钮位置与反馈 |

**交付**：`tech_design §5` 定稿；`03_product_design.md` 中各用例交互草稿完成，可直接进入 Phase 04 开发。

**学习点**：前端框架调研、部署方案对比、从用例到界面的设计转化。

---

### Phase 04 · MVP 开发与上线

> 详细文档：[`04_mvp_launch.md`](04_mvp_launch.md)  
> ✅ **P0 已完成**（2026-04-12）：S1 `backend/` API、CORS、`backend/static` 与语义检索阈值；**S2** UC-01；**S3** UC-02 Modal；SQLite `check_same_thread=False`。**S4** Fly.io（`sin`）+ volume 内 DB + GitHub Actions（`environment: prod` + `FLY_API_TOKEN`）+ 公网 / 大陆抽验与 CI 已通过。UC-03/04（P1）见 `04_mvp_launch.md`。  
> ⚠️ 技术前置：Phase 03 完成

**目标**：按 Phase 03 的设计，把 UC-01～UC-02（P0）开发完成并部署上线；UC-03／UC-04（P1）量力而行。

**交付**：公开可访问的 MVP 网站；UC-01 + UC-02 功能完整可用；满足 Phase 04 验收标准。

**学习点**：Web 全链路开发（前端 + API + 部署）、检索结果展示优化。

---

### Phase 05 · UX 改版 · 搜索优化 · 以图搜图

> 详细文档：[`05_ux_and_search.md`](05_ux_and_search.md)  
> 🔄 **进行中**
> ⚠️ 技术前置：Phase 04 完成

**目标**：根治「构图相似搜索」精度问题（pipeline 侧标注升级）；上线 CLIP 以图搜图（UC-05）；视觉动态排版改版。

**关键决策**（在 `05_ux_and_search.md` 中确定）：
- 标注新增 `composition` 字段（构图/空间关系/抽象形状），embedding 拼接策略
- 以图搜图：CLIP image embedding（Jina CLIP v2 API）独立索引，不走 text 中转；与现有 text embedding 并列双空间
- description 访问控制：用户侧隐藏 + `?debug=1` 后门

**交付**：全量重标注 + 重 embed 完成；UC-05 上线；新 Masonry 自适应比例排版；验收见 `05_ux_and_search.md`。

---

## 参考产品

| 站点 | 形态 | TNJ 可借鉴 | 与 TNJ 的差异 |
|------|------|-----------|--------------|
| [Frinkiac](https://frinkiac.com) | 辛普森台词 → 截帧 + meme 生成 | 单一 IP 专项索引的产品形态；视频帧采集路径 | 台词精确匹配驱动；TNJ 以氛围/情绪语境驱动 |
| [YARN](https://tv-memes.yarn.co) | 多剧 TV 梗图，按台词/片段检索 | 「按语境找画面」的搜索体验设计 | 多来源泛平台；TNJ 单 IP 专注度更高 |
| [memeSRC](https://memesrc.com) | 跨剧「梗图源图」检索与工具 | 搜索结果卡片设计与素材工具化思路 | 通用引擎；TNJ 垂直专项 + 语义驱动 |
| [iCatMeme](https://icatmeme.com) | 猫 meme 专题，标签/分类浏览 | 垂直专题站的信息架构与标签体系设计 | 以标签筛选为主；TNJ 需加自然语言语义层 |
| [Cat Meme Multiverse](https://cats.mixedbread.com) | 猫 meme 语义检索 demo | NL 查询 → 相关 meme 的前端交互参考 | 技术 showcase；TNJ 需要完整自建数据管线 |

---

## 维护说明

- **状态更新**：`tech_design` 对应节定稿后，在 Phase 总览表中更新状态；Phase 文档完成后更新为「进行中 / 已完成」。
- **需求引用**：Phase 子文档中用功能编号（`MVP-Fxx`）引用需求，不在此重复。
