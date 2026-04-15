# Phase 05 — UX 改版 · 搜索优化 · 以图搜图

> 状态: **进行中** | 依赖: Phase 04 ✅  
> 目标: 根治构图搜索精度问题；**S2 以图搜图（UC-05）✅（2026-04-15）**；视觉动态排版改版。

---

## 功能范围

| 功能 | 优先级 | 说明 |
|------|--------|------|
| 标注 prompt 改版 + 全量重跑 | P0 | 新增 `composition` 字段，全量重标注 + 重 embed |
| 以图搜图（UC-05） | P0 | 搜索框旁上传图片，CLIP image embedding，返回视觉结构相似截图 |
| 视觉动态排版 | P0 | 卡片按原始宽高比自适应；description 隐藏 + debug 后门 |
| 搜索产品侧优化 | P1 | query 示例构图导向；空结果引导语更新 |

**不在范围**：新数据采集扩量；用户账号系统；UC-03 标签筛选；UC-04 素材复用。

---

## 步骤总览

| # | 步骤 | 核心产出 | 验收标志 |
|---|------|---------|---------|
| S1 | 标注 prompt 改版 + 全量重跑 | `composition` 字段全量写入；向量索引重建 | ✅ 已完成（2026-04-14）：全量重标 + `embed --force` + 生产 DB 覆盖；构图类 Top-5 见 `eval_memo.md` 可补录 |
| S2 | 以图搜图（UC-05） | `POST /api/search/image`；CLIP 双索引；搜索框相机图标 | ✅ 已完成（2026-04-15）：全库 `item_image_embeddings` + 生产 `JINA_API_KEY`；前端互斥态与校验已验收 |
| S3 | 视觉改版 | 自适应比例 Masonry；description 隐藏 + debug 后门 | `?debug=1` 可见 description；正常访问不可见 |
| S4 | 搜索产品侧优化（P1） | placeholder / 空结果文案更新 | 文案引导用户描述构图而非情绪 |

---

## S1 · 标注 prompt 改版 + 全量重跑

### 问题根因

在引入 `composition` 之前，prompt（S2-v2）要求「只描述图片中可见的客观内容，不做情感推断或叙事延伸」，annotation 偏向**字面场景描述**。

TNJIndex 的核心用例是**构图/视觉结构相似**匹配——用户看到一张画面，联想到猫鼠里有张图的「形」几乎一样（如：一人俯视倒地者；抽象几何形状撞车）。当前标注完全缺失这个维度，导致搜索精度低。

### 新增字段：`composition`

在 `pipelines/prompts.py` 的 JSON 输出中增加 `composition` 字段：

```json
{
  "title": "...",
  "tags": [...],
  "description": "...",
  "composition": "..."
}
```

**`composition` 字段要求**（写入 prompt）：

> 从**视觉结构**角度描述这张图，覆盖以下三点，总长 ≤ 200 字符：  
> ① **镜头/视角**：俯视 / 仰视 / 平视 / 特写 / 全身 / 广角  
> ② **角色空间关系**：如「一角色从高处俯视另一躺倒角色」「两角色面对面对峙」「单角色居中大特写」「角色背对摄像机」「多角色追逐排成一线」  
> ③ **抽象视觉形状**：整体画面抽象成几何形状或动势线，如「三角形构图」「左右对称」「大面积空白背景 + 单点角色」「弧形动势」「垂直分割双画面」  
> 不描述角色名字、剧情、情绪。只描述视觉结构本身。

**prompt 示例输出**（供标注一致性参考）：

| 画面 | 期望 `composition` |
|------|--------------------|
| Tom 从高处俯身怒吼，Jerry 躺在地上戴着皇冠 | 俯视视角；站立角色从画面上方俯视躺倒角色；对角线构图，上强下弱 |
| Jerry 操控大型火炮，炮管斜向右上角延伸 | 平视侧身；单角色居画面左下，大型道具斜线延伸至右上；斜线主导 |
| Tom 与 Jerry 隔桌正面对峙，各占半边画面 | 平视；两角色左右对称，各占画面一半；中轴对称构图 |

### DB Schema 迁移

`items` 表增加 `composition TEXT` 列（可为空，迁移时老数据补填）：

```sql
ALTER TABLE items ADD COLUMN composition TEXT;
```

### Embedding 策略更新

embed 输入文本由 [`pipelines/embed.py`](pipelines/embed.py) 的 `_embed_input_text` 拼接：**非空**的 `description`、`composition`、tags 空格串，按该顺序用空格连接（与「先语义描述、再构图摘要、再关键词」一致）。不改变向量维度，无需改 sqlite-vec 表结构。

### 重跑流程

1. 更新 `pipelines/prompts.py`，新增 `composition` 字段说明
2. DB migration：`ALTER TABLE items ADD COLUMN composition TEXT`
3. 全量重标注（`pipelines/annotate.py`，写入 `composition`）
4. 全量重 embed（`pipelines/embed.py`，`--force` 重建 `item_embeddings`）
5. 更新 `pipelines/eval_memo.md`，记录 S1-v3 与构图类 query（Top-5 可后续用 `search_cli` 补录）

### 验收

- [x] DB 中所有已标注 Item 均有 `composition` 非空值（全量重标 + 校验；仍为 `raw` 的条目除外）
- [x] `eval_memo.md` 已增加 S1-v3 完成记录；构图类 query ≥3 条见该节（Top-5 id 可用 `pipelines.search_cli` / `search()` 在配置 embed 密钥后补录）
- [x] `pipelines/prompts.py` 注释版本号 **S1-v3**（2026-04-14）

---

## S2 · 以图搜图（UC-05）

### 场景与技术方案选择

TNJIndex 的核心用例是**跨域视觉结构匹配**：用户看到某个画面（其他动漫帧、真实照片、几何图形），想找猫鼠里「形相似」的截图——**内容可以完全无关**（典型：电路图线条形状 ↔ Jerry 操控大炮的构图走势）。

业界针对此类 **Cross-domain Visual Structure Retrieval** 的标准方案是 **CLIP image embedding**，而非 vision→text→embed（text-mediated）。原因：LLM 会把电路图描述为「电阻电容运放」，把大炮描述为「Jerry 操控火炮」——在 text embedding 空间里两者毫无关联，视觉结构信息在文字化时已丢失。CLIP 直接在视觉特征空间计算相似度，绕过了这一信息损耗，是 Google Photos、Pinterest 等图像检索系统的底层共识。

### 架构设计

以图搜图使用独立的图像 embedding 空间，与现有 text embedding 并列，互不干扰：

```
文字搜索：query text → text embed → KNN on item_embeddings（1536-dim）
以图搜图：query image → CLIP encode → KNN on item_image_embeddings (1024-dim)
```

查询链路：

```
用户上传图片
    ↓
POST /api/search/image（multipart）
    ↓
后端：CLIP encode 上传图片 → 1024-dim 向量（< 500ms）
    ↓
KNN 搜索 item_image_embeddings 表
    ↓
返回 Top-K（同现有 SearchResponse 格式）
```

### Model 选型

**推荐：Jina CLIP v2 API**（`jina-clip-v2`）

| 维度 | 说明 |
|------|------|
| 向量维度 | 1024-dim |
| 中国大陆可访问 | ✅（开发环境） |
| 新加坡服务器可访问 | ✅（fly.io `sin`） |
| 费用 | $0.02 / 1000 images；全库初始化 < $0.01；单次 query 近乎免费 |
| 硬件要求 | 无 GPU，纯 REST API，与现有 embed_client 模式一致 |

**备选：本地 open_clip ViT-B/32**

| 维度 | 说明 |
|------|------|
| 费用 | $0（API 费用） |
| M4 Mac（开发） | MPS 加速，单张 < 100ms |
| fly.io 1 CPU（生产） | CPU 推理约 1–2s/次，可接受 |
| 适用场景 | Jina API 不可用时的 fallback；或全部本地化部署 |

> OpenAI 无官方 CLIP API；Voyage multimodal-3 质量更高但新加坡节点访问稳定性待验；DashScope 暂无对等 image embedding 接口。

### DB Schema

新增独立 sqlite-vec 表（维度不同，不与 text embedding 表共用）：

```sql
-- 与仓库 pipelines/sqlite_vec.py 中 vec0 定义一致
CREATE VIRTUAL TABLE IF NOT EXISTS item_image_embeddings USING vec0(
  image_embedding float[1024],
  +item_id INTEGER
);
```

### 索引建立流程（一次性批量）

1. `pipelines/clip_embed.py`：封装 Jina CLIP v2 API 调用
2. `pipelines/clip_embed_all.py`：批量对全库已标注条目编码，写入 `item_image_embeddings`
3. `scrapers/ingest.py`：新图入库时自动追加 CLIP encode 步骤

### API 设计

```
POST /api/search/image
Content-Type: multipart/form-data

参数：
  file: 图片文件（JPEG / PNG / WEBP，≤ 5MB）
  limit: int = 12（可选）

响应：同 GET /api/search 的 SearchResponse 格式
```

### 前端设计

**搜索框区域布局**：

```
┌───────────────────────────────────────────┬──────────┬──────────┐
│  描述你想找的画面构图…                    │  [📷]   │ [ 搜索 ] │
└───────────────────────────────────────────┴──────────┴──────────┘
```

- `[📷]` 为相机图标按钮（`16px`，辅色），hover 提示「上传图片搜索」
- 点击触发隐藏 `<input type="file" accept="image/*">`
- 选择文件后立即触发 `POST /api/search/image`，**清空文字搜索框**

**以图搜索状态**：

| 状态 | 呈现 |
|------|------|
| 上传中 / 编码中 | 搜索框内显示「正在分析画面…」；相机图标变 spinner；预计 1–3s |
| 有结果 | 结果区 header：`「以图搜索」的相似结果（N 条）`；相机图标旁显示缩略图预览（20px 圆角小图） |
| 空结果 | 「未找到视觉结构相似的截图，换一张图试试？」 |
| 文件过大 / 格式不对 | Toast 提示「仅支持 JPEG/PNG/WEBP，≤ 5MB」 |
| 搜索出错 | Toast 提示「图像分析出错，请稍后重试」 |

**状态切换**：以图搜索与文字搜索互斥——开始以图搜索时清空文字；在搜索框输入文字时清除图片状态。

### 验收

- [x] 全库 `item_image_embeddings` 写入完成，无空值
- [x] 上传图片可返回 Top-12 视觉结构相似截图
- [x] UI 加载态、空结果态、错误态均正常展示
- [x] 文件大小 / 格式校验在前端生效
- [x] 与文字搜索状态互斥，无状态交叉

---

## S3 · 视觉改版

### 动态排版（小红书风格 Masonry）

**现状问题**：卡片可能被裁剪为固定高度，横版图看起来扁、竖版图看起来被截断。

**改版目标**：每张卡片高度由图片**原始宽高比**自然决定，不裁剪内容。

**实现方式**：
- `<img>` 不设固定 `height`，使用 `width: 100%` + `height: auto`
- 去掉 ImageCard 内的 `aspect-ratio` 固定值（如有）
- Masonry 列宽固定，行高完全由图片比例撑开
- 保持 `object-fit: contain`（不拉伸）或直接不设 `object-fit`（自然尺寸）

**列数**（与现有设计保持一致）：PC 4 列 / 平板 2 列 / 手机 1 列

### Description 管理

**背景**：`description` 是 AI 生成的字面描述，不适合直接展示给用户（观感幼稚），但需要保留供标注质量调优使用。

**改动范围**：

| 位置 | 现状 | 改后 |
|------|------|------|
| DetailModal 正文区 | 展示 description | 隐藏，不渲染 |
| DetailModal（`?debug=1`） | — | 底部增加折叠区「调试信息」，展示 `description` + `composition`（灰色小字） |
| 搜索结果卡片 | 无 description | 不变 |

**Debug 后门实现**：
```typescript
// 纯前端，无需后端改动
const isDebug = new URLSearchParams(window.location.search).has('debug')
// DetailModal 底部条件渲染 <DebugPanel description={...} composition={...} />
```

**`/api/items/{id}` 响应**：继续返回 `description` 和 `composition` 字段（后端不改），前端按 `isDebug` 控制是否渲染。

### 验收

- [ ] Masonry 卡片高度自然跟随图片比例，无裁剪
- [ ] 正常访问 DetailModal 中无 description 文字
- [ ] 访问 `/?debug=1` 后打开任意 Modal，底部可见 description + composition
- [ ] 视觉风格与现有色彩系统（`#0f0f0f` 背景、橙色强调色）保持一致

---

## S4 · 搜索产品侧优化（P1）

### Placeholder 更新

将搜索框的随机 placeholder 示例更换为**构图导向**，引导用户描述视觉结构而非情绪：

**现有示例**（情绪导向）：「一脸嫌弃」「被催婚时的心情」「假装没听见」

**新示例**（构图 + 使用场景混合）：

```
「一个人从高处俯视另一个倒在地上的人」
「两人隔着东西剑拔弩张对视」
「角色扭头背对镜头」
「一大一小，大的追着小的跑」
「角色正在操作一个巨大的机器/设备」
「特写：嘴巴大张，眼睛瞪圆」
```

### 空结果引导语更新

```
没找到相关截图。

试试描述画面的构图，例如：
「一人站着另一人躺着」「两角色对峙」「单角色特写大张嘴」
```

### 验收

- [ ] Placeholder 示例更新，包含 ≥ 4 条构图类描述
- [ ] 空结果页引导语包含构图示例

---

## 非目标（本阶段不做）

- UC-03 标签筛选 / UC-04 素材复用——延后处理
- 更换为更高质量 CLIP 模型（如 DINOv2）并重建索引——待 UC-05 上线后评估效果再决策
- 用户账号 / 收藏功能
- 新数据扩采
- 图片上传到 OSS / 用户生成内容
