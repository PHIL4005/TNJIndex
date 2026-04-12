# Phase 02 — AI 标注与索引

> 状态: **✅ 已完成**（M1–M3 / S1～S8 已落地；固定查询集见 `pipelines/eval_queries.txt`，抽检记录见 `pipelines/eval_memo.md`）| 依赖: Phase 01 ✅；`tech_design` §3 §4 定稿  
> 目标: 跑通「缩略图 → Vision 标注 → 文本 embedding → sqlite-vec」全链路；**CLI + 本地极简网页** 用自然语言检索，**以真实图片展示** 做数据与主观双重验收。

---

## 功能范围

| 功能 | 描述 | 优先级 |
|------|------|--------|
| Vision 标注管线 | 读取 `annotation_status = raw` 的 Item，用缩略图调 Vision API（JSON mode），写回 `title` / `tags` / `description`，状态改为 `annotated`；支持 `--limit`、失败保留 `raw` 与可重试 | P0 |
| Embedding 与向量表 | 对 `annotated` 条目将 `description` + `tags` 拼接后调用 embedding API，写入 `item_embeddings`（sqlite-vec，与 `tech_design` §4 一致） | P0 |
| 语义检索（核心） | 用户查询文本 embed 后，在向量空间做 ANN（余弦等），返回 Top-K **按语义相似**，非字面 `LIKE` 关键词命中 | P0 |
| CLI 检索 | 终端输入查询字符串，输出 Top-K 的 `id`、`score`、关键字段，便于脚本化与回归对比 | P0 |
| 本地可视化测试页 | 仅开发自测：浏览器访问本地服务，输入同一查询，**展示 Top-K 对应缩略图或原图**（及可选 `title`/`tags`/分数），便于从画面与元数据两侧判断检索是否合理；与 CLI **共用同一检索函数/SQL** | P0 |
| 全量批跑与统计 | 全库标注 + 全量建向量；输出成功/失败条数与费用估算（若 API 提供用量） | P0 |
| 固定查询集抽检 | 10～20 条固定查询（整句 + 若干关键词 + 可选中英混合），在**测试页**上对每条查看 Top-5；记录模型版本与不通过样例 | P0 |

---

## 不在范围

| 项目 | 归属 |
|------|------|
| UC-03 标签筛选（`JSON_EACH` 等 SQL 过滤）、标签面板 API | Phase 03 / Phase 04（见 `tech_design` §4「结构化标签过滤」） |
| FTS5 等纯词法全文索引 | 非本 Phase 必选项；语义需求由 embedding 满足，日后若需要再评估 |
| 产品级前端（React/Vercel）、对外部署、UC-01～UC-04 正式交互 | Phase 03 设计 + Phase 04 开发 |
| 对象存储迁移、Fly.io 持久化 | Phase 03 前或 Phase 04（见 `tech_design` §2 / §5） |
| 再次扩量爬虫（如 Imgflip） | 按需，不阻塞本 Phase 验收 |

---

## 用户故事（开发者视角）

- 作为开发者，我可以对 `raw` 批量跑 Vision 标注并写回 DB，以便每条素材都有可 embed 的文本描述与标签。
- 作为开发者，我可以为已标注条目生成向量并写入 sqlite-vec，以便自然语言查询走 ANN 而非关键词匹配。
- 作为开发者，我可以在 CLI 与本地网页用**同一查询**得到**一致**的 Top-K 列表，并在网页上**直接看到图片**，以便结合元数据做抽检与调 prompt / 换模型。

---

## 验收标准

### 数据与管线

- [x] 全库 `items` 中 `annotation_status = 'annotated'` 的记录数 = 计划处理条数（与 Phase 01 入库总量一致，或减去明确排除的失败条并有清单）。**M3**：失败仍为 `raw` 的 id 见 `pipelines/annotate_known_failures_m3.txt`。
- [x] 每条 `annotated` 记录满足 `tech_design` §1：`title` 格式约束、`tags` 非空数组、`description` 在长度上限内。
- [x] `item_embeddings`（或 §4 约定的虚拟表名）中，每个应参与检索的 `annotated` Item 均有对应向量行，维度与所选 embedding 模型一致。

### 检索与一致性

- [x] CLI：输入任意查询字符串，可打印 Top-K（默认 K 与 `tech_design` §4 示例一致，如 10）。
- [x] 本地测试页：输入**相同**查询，列表顺序与 CLI **一致**（同一检索实现）；**每条结果展示对应图片**（优先缩略图路径，缺失时降级原图），并展示足够判断是否「像那么回事」的元数据（至少 `id`，建议含 `title`/`tags`/`description` 片段与距离分）。
- [x] 测试页仅用于本地开发（默认绑定 `127.0.0.1` 或文档中明确「勿暴露公网」）；不要求与 Phase 04 最终 UI 一致。

### 质量抽检（主观）

- [x] 维护固定 **10～20 条**查询集（覆盖：完整句子、几个关键词、可选 2～3 条较抽象表述）。路径：`pipelines/eval_queries.txt`。
- [x] 对每条查询在测试页查看 **Top-5**：采用**宽松**通过标准——至少 **1 条**与查询意图明显相关；不通过的查询记录到简短备忘录（查询原文、日期、Vision/Embedding 版本、Top-5 的 `id`），便于后续迭代。记录：`pipelines/eval_memo.md`（含 Top-5 id；**建议在带图页再做目视**后更新结论）。
- [x] 将查询集文件名或路径写入本仓库文档/注释（如 `pipelines/eval_queries.txt`），便于回归。

### 工程

- [x] `pyproject.toml`（或等价）已声明 Phase 02 所需依赖（Vision SDK、Embedding SDK、sqlite-vec 加载方式等），`README` 或本节「技术说明」中有本地运行测试页的命令。
- [x] 若实测后选定 Vision/Embedding 具体型号，已回写 `docs/architecture/tech_design.md` §3 / §4 相应段落（与路线图维护说明一致）。

---

## 步骤总览

| # | 步骤 | 产出 | 验收方式 |
|---|------|------|---------|
| S1 | 依赖与 sqlite-vec | 可加载扩展的 Python 环境；DB 侧向量表/虚拟表就绪 | 空库或样例数据上执行一次建表/写入向量查询无报错 |
| S2 | Vision 小样本实测 | 选定模型与定稿 prompt（写入 `tech_design` §3） | 10～20 张典型图 JSON 字段合法、人工目视可接受 |
| S3 | `pipelines/annotate.py` | 批量标注、`--limit`、失败不重标记为成功 | 小批量 `raw` → `annotated`，失败条仍为 `raw` 且有日志 |
| S4 | Embedding 写入 | `pipelines/embed.py`（或等价模块）写入 `item_embeddings` | 已标注样本均有向量；重启后可 ANN 查询 |
| S5 | 检索核心 + CLI | 单处封装「query 文本 → Top-K rows」 | CLI 返回与 SQL/vec 距离一致 |
| S6 | 本地可视化测试页 | 本地 HTTP 服务 + 结果页展示图片与元数据 | 同查询与 S5 输出一致；浏览器可见图 |
| S7 | 全量标注与建索引 | 全库 `annotated` + 全量向量 | 统计脚本输出成功/失败计数 |
| S8 | 固定查询抽检与收尾 | 抽检记录、文档更新 | 满足上文「质量抽检」与 Phase 02 关门条件 |

---

## S1 · 依赖与 sqlite-vec

**目标**: 在开发机可复现地启用 sqlite-vec，并与现有 `tnjindex.db` 同库管理。

**任务**:

- [x] 在依赖中固定 sqlite-vec 的引入方式（官方文档推荐的 Python 绑定或 `sqlite3` 扩展路径），并在初始化 DB 的代码路径中创建 `item_embeddings`（或 §4 约定结构）。
- [x] 向量维度与后续选定的 embedding 模型一致（未定稿前可用占位维度，S2 后修正）。

**验收**:

- [x] 文档或脚本中有一条「最小向量写入 + 最近邻查询」的验证步骤可通过。

---

## S2 · Vision 小样本实测

**目标**: 按 `tech_design` §3 流程，在 10～20 张图上对比候选模型，锁定默认 Vision 模型与 prompt。

**任务**:

- [x] 记录 token 与费用样本；将最终 prompt 与模型名写入 `tech_design.md` §3。

**验收**:

- [x] 输出 JSON 可解析；`title`/`tags`/`description` 符合 §1 约束；人工抽查无系统性胡编。

---

## S3 · `pipelines/annotate.py`

**目标**: 生产级标注批处理（读缩略图、调 API、写回、状态机）。

**任务**:

- [x] 仅处理 `annotation_status = raw`；成功则 `annotated`，失败则保持 `raw` 并记录原因（日志或 `error_log` 表二选一，文档写明）。
- [x] 支持 `--limit N` 增量与断点续跑（避免重复扣费：已 `annotated` 跳过）。

**验收**:

- [x] 对 ≥20 条 `raw` 试跑，DB 状态与字段符合预期。

---

## S4 · Embedding 写入

**目标**: 对已标注文本生成向量并关联 `item_id`。

**任务**:

- [x] 拼接规则与 `tech_design` §4 一致：`description` + `tags`（空格拼接）。
- [x] 支持仅对「尚无向量或文本已更新」的条目重算（至少文档约定策略：全量重跑或按版本号）。

**验收**:

- [x] `SELECT COUNT(*)` 与应索引的 `annotated` 条数一致（在约定策略下）。

---

## S5 · 检索核心 + CLI

**目标**: 单一真相源的检索逻辑，供 CLI 与网页调用。

**任务**:

- [x] 实现 `embed(query)` + `vec_distance` 排序 + `JOIN items` 取展示字段。
- [x] CLI 入口（如 `uv run python -m pipelines.search_cli "..."`）打印 Top-K。

**验收**:

- [x] 手工构造 2～3 条查询，结果顺序与直接 SQL 一致。

---

## S6 · 本地可视化测试页

**目标**: **用真实图片展示检索结果**，便于主观与数据双重判断；实现方式从简（FastAPI + Jinja 单页、或静态页调本地 API、或 Gradio/Streamlit 等任选其一）。

**任务**:

- [x] 页面展示：查询框、提交后 **Top-K 图片网格**（`thumbnail_path` / `image_path` 映射到可访问 URL 或 `file://` 约定——推荐通过静态路由 `/media/...` 映射本地 `data/images`）。
- [x] 每条卡片展示：`id`、相似度分数、关键文本字段（便于对照「搜到的图」与「标注是否离谱」）。
- [x] 调用 S5 同一检索函数，禁止复制粘贴第二套 SQL。

**验收**:

- [x] 任意查询在 CLI 与页面结果 **id 顺序一致**；页面可清晰辨认每张图的内容。

---

## S7 · 全量标注与建索引

**目标**: 对 Phase 01 全量 `raw` 跑完标注，并写入全量向量。

**验收**:

- [x] `annotated` + 向量条数与计划一致；控制台或日志输出汇总统计。

---

## S8 · 固定查询抽检与收尾

**目标**: 完成 10～20 条固定查询的 Top-5 人工检视，并固化查询集与结论。

**验收**:

- [x] 满足「验收标准 · 质量抽检」；不通过样例有记录；必要时在 `tech_design` §3 微调 prompt 并重跑受影响子集（文档注明）。

---

## 技术说明

- **架构与字段**: 以 `docs/architecture/tech_design.md` §1 §3 §4 为准；embedding 不存 `items` 表，仅存向量表。
- **索引技术**: 本 Phase **仅**依赖 **文本 embedding + sqlite-vec ANN** 满足「自然语言 / 关键词式短句 → 语义相似」；**不**将 UC-03 标签过滤、FTS5 列入本 Phase 交付。
- **影响模块（预期）**: `pipelines/annotate.py`、`pipelines/embed.py`、检索与 CLI 模块、本地测试页入口、`scrapers/db.py`（若需迁移/新表）。
- **注意事项**: API Key 与计费上限放在环境变量或本地 `.env`（勿提交仓库）；大批量跑之前先用 `--limit` 试跑。
- **本地测试页**：`uv run python -m pipelines.app`（默认 `127.0.0.1:8000`，勿对公网暴露）。命令亦见 [`docs/README.md`](../README.md)。

---

## 任务清单（勾选跟踪）

- [x] S1 依赖与 sqlite-vec
- [x] S2 Vision 实测与 `tech_design` §3 更新
- [x] S3 `annotate.py`
- [x] S4 `embed.py`（或等价）
- [x] S5 检索核心 + CLI
- [x] S6 本地可视化测试页（**结果须含图片**）
- [x] S7 全量跑通
- [x] S8 固定查询抽检与记录
- [x] 若架构有变：更新 `docs/architecture/tech_design.md` 并同步 `00_roadmap.md`

---

## S2-v2 · 重标注（2026-04-12）

**触发原因**：S8 目视验收（见 `pipelines/eval_memo.md`）发现原 Vision 标注存在系统性质量问题：
- `description` 为"梗图解说体"，充斥情感推断与叙事，与用户实际搜索输入脱节
- `tags` 缺少构图/镜头词与搜索语境词（如「被迫营业」「一脸嫌弃」）
- 部分图（如 id=89）存在事实性误标（把对峙构图标为「手榴弹」场景）

**变更内容**：
- 重写 `pipelines/prompts.py`：新 prompt 要求只描述可见客观内容，`tags` 覆盖五类（角色/构图/动作/道具/搜索词），`description` = 客观描述句 + 搜索短句
- 升级模型：`DEFAULT_MODEL_DASHSCOPE` → `qwen3.6-plus`
- `pipelines/annotate.py` 新增 `--force`（重标注已 annotated 条目）、`--enable-batch`（DashScope Batch File API，约 50% 费率）
- 新增 `pipelines/batch_utils.py`：Batch File API 封装，含 `enable_thinking=false`

**重跑命令**：
```bash
# 实时测试 10 张
TNJ_VISION_PROVIDER=dashscope uv run python -m pipelines.annotate --force --limit 10

# 全量 Batch（50% 费率）
TNJ_VISION_PROVIDER=dashscope uv run python -m pipelines.annotate --force --enable-batch

# 全量重建向量
uv run python -m pipelines.embed --force
```
