# Phase 04 — MVP 开发与上线

> 状态: **进行中** | 依赖: Phase 03 ✅（含 OSS 图片迁移）  
> 进度: **S1–S2 ✅**（后端 API + 本地 UC-01 搜索页已验收）；**S3** UC-02 Modal、**S4** 部署与 CI/CD 待办。  
> 目标: 按 Phase 03 设计完成 UC-01/02 并部署上线；UC-03/04（P1）完成后追加。

---

## 功能范围

| 功能 | 优先级 | 说明 |
|------|--------|------|
| Backend API（3 端点） | P0 | `/api/search`、`/api/items/{id}`、`/api/tags` |
| 搜索质量优化 | P0 | S1 诊断 + Phase 02 S2-v2 标注/向量侧已改善；可选 FTS5 等见 S1 checklist |
| 前端 UC-01 自然语言搜索 | P0 | 搜索框 + Masonry + 无限滚动 + 全状态覆盖（**本地已交付**，2026-04-12） |
| 前端 UC-02 素材详情 Modal | P0 | 大图 + 标签 + 描述 + 多种关闭方式 |
| Dockerfile + Fly.io 部署 | P0 | 香港节点，含 persistent volume（SQLite）|
| GitHub Actions CI/CD | P0 | push main 自动 build + deploy |
| UC-03 标签筛选 | P1 | Phase 04 上线后追加 |
| UC-04 素材复用（复制链接） | P1 | Phase 04 上线后追加 |

**不在范围**：新数据采集、用户账号系统、`pipelines/` 脚本改动

---

## 目录结构

```
TNJIndex/
├── backend/
│   ├── __init__.py
│   ├── main.py               # FastAPI 入口；注册 /api 路由 + StaticFiles mount
│   ├── deps.py               # DB 连接依赖（get_db，供 routers 注入）
│   ├── schemas.py            # Pydantic 响应模型
│   └── routers/
│       ├── __init__.py
│       ├── search.py         # GET /api/search
│       ├── items.py          # GET /api/items/{id}
│       └── tags.py           # GET /api/tags
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── SearchBar.tsx       # 搜索框 + 热门标签快捷入口
│   │   │   ├── MasonryGrid.tsx     # 瀑布流容器 + 无限滚动
│   │   │   ├── ImageCard.tsx       # 单卡片（hover 态 + 橙色边框）
│   │   │   └── DetailModal.tsx     # UC-02 大图 Modal
│   │   ├── hooks/
│   │   │   ├── useSearch.ts        # /api/search 调用与状态管理
│   │   │   └── useInfiniteScroll.ts
│   │   ├── lib/
│   │   │   └── api.ts              # fetch 封装 + TS 类型定义
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── index.html
│   ├── vite.config.ts              # build.outDir: "../backend/static"
│   └── package.json
│
├── pipelines/                      # 保持现状，数据处理管线（不在本 Phase 改动）
├── Dockerfile                      # 多阶段：Stage 1 Node build → Stage 2 Python serve
├── fly.toml
└── .github/
    └── workflows/
        └── deploy.yml
```

**关于 `pipelines/app.py`**：该文件为本地开发测试用 FastAPI 应用，Phase 04 完成 `backend/` 后废弃（可删除）。

---

## 步骤

### S1 · 后端 API + 搜索质量优化

**目标**：搭建生产 `backend/` 模块，3 个 API 端点本地可用；同步诊断修复搜索质量，确保检索效果满意后再开前端。

#### API 搭建

- [x] 创建 `backend/` 模块，`main.py` 配置：
  - [x] `/api` 路由前缀（须在 StaticFiles 之前注册）
  - [x] `StaticFiles(directory="backend/static", html=True)` mount 到 `/`（目录存在时挂载；`npm run build` 后产物写入 `backend/static`）
  - [x] CORS 中间件（开发阶段允许 `http://localhost:5173`）
- [x] `deps.py`：`get_db()` 依赖，返回 sqlite-vec 已加载的 `sqlite3.Connection`
- [x] `schemas.py`：定义响应模型
  - `ItemSummary`（id, title, `thumbnail_url`，tags，score）
  - `ItemDetail`（id, title, `image_url`，`thumbnail_url`，tags, description）
  - `TagCount`（name, count）
- [x] `routers/search.py`：`GET /api/search?q=&tags=&limit=&offset=`，调用 `pipelines/search.py`；语义路径 **distance 阈值**（环境变量 `SCORE_THRESHOLD_MAX`，默认 `1.0`）在 router 层过滤远距结果
- [x] `routers/items.py`：`GET /api/items/{id}`
- [x] `routers/tags.py`：`GET /api/tags`，按出现频次排序
- [x] 废弃 `pipelines/app.py`（模块顶部 `DeprecationWarning`）

#### ⚠️ 搜索质量诊断与优化

> **更新（2026-04-12）**：S1-a 目视 + 复盘认定**主因是 Vision 标注文本**（旧 prompt / 模型），而非 sqlite-vec 或纯「中文 query」问题。已通过 **S2-v2**（`pipelines/prompts.py`、`qwen3.6-plus`、全量 `annotate --force`、`embed --force`、`pick_image_for_vision` OSS）显著改善主观检索；详见 `pipelines/eval_memo.md`、`docs/mvp/02_annotation_index.md` S2-v2。  
> **S1 本段 checklist**：诊断与「标注+向量」侧优化已在 Phase 02 闭环；**FTS5 / query 扩写** 等项留作 Phase 04 若仍不满意再评估（非 S1 前置阻塞）。

可能原因（历史排查表，已对照）：

| 方向 | 具体问题 |
|------|---------|
| 查询预处理 | 中文 query 直接 embed，与索引时的"中英混合 description+tags"存在语言分布偏差 |
| 向量相似度 | sqlite-vec 默认距离度量是否与 embedding 模型匹配（L2 vs cosine）|
| 召回策略 | 仅纯向量检索，无关键词兜底；少见标签或精确词无法命中 |
| top-k | 固定 k=10 可能过少，分页场景需支持更大 offset |
| **标注质量（S2-v2 主因）** | description/tags 与画面及用户检索词脱节 → 已用新 prompt + 重 embed 处理 |

诊断方式：用 `pipelines/eval_queries.txt` 固定查询集跑当前结果，人工标注相关性，再对比改动后结果。

- [x] 诊断：固定查询集 + 目视；根因见 `eval_memo.md`
- [x] 标注与向量侧优化：S2-v2（Phase 02），非本 Phase 04 代码
- [ ] （可选）若上线后仍弱：query 预处理 / cosine / FTS5 等——按需另开任务

**验收**：
- [x] `uv run uvicorn backend.main:app --reload` 本地启动无报错
- [x] curl 3 个端点返回符合 schema 的 JSON
- [x] 固定查询集主观检索：S2-v2 后已确认明显改善（`eval_memo.md`）

---

### S2 · 前端搭建 + UC-01 搜索页

**目标**：初始化 React/Vite 项目，配置设计系统，完成搜索主页全部交互与状态。

#### 项目初始化

- [x] `frontend/` 初始化（Vite + React + TypeScript）
- [x] 安装依赖：shadcn/ui、Tailwind CSS v4、`react-masonry-css`
- [x] 配置 Tailwind 色彩 token（深色主题，对齐 Phase 03 S3 色彩方案）：

  | Token | 值 | 用途 |
  |-------|----|------|
  | `background` | `#0f0f0f` | 页面底色 |
  | `surface` | `#1c1c1e` | 卡片/面板/Modal |
  | `border` | `#2c2c2e` | 描边/分隔线 |
  | `accent` | `#f97316` | 按钮/标签高亮/链接 |
  | `foreground` | `#f4f4f5` | 正文/标题 |
  | `muted` | `#71717a` | 元数据/次要信息 |

- [x] `vite.config.ts`：`build.outDir: "../backend/static"`；开发代理 `/api` → `localhost:8000`
- [x] `lib/api.ts`：fetch 封装，类型定义对齐 backend schemas

#### UC-01 实现

- [x] `SearchBar.tsx`：搜索框 + Enter/按钮触发；placeholder 随机轮换示例短语
- [x] `ImageCard.tsx`：缩略图卡片；hover `scale-[1.02]` + 橙色细边框，过渡 150ms
- [x] `MasonryGrid.tsx`：瀑布流（PC 4列 / 平板 2列 / 手机 1列）
- [x] `useSearch.ts`：搜索状态管理（loading / data / error / empty）
- [x] `useInfiniteScroll.ts`：IntersectionObserver 触底加载下一页
- [x] 热门标签区：调用 `/api/tags` 取前 8，点击直接触发搜索（依赖 `scrapers/db.py` 中 `check_same_thread=False`，避免 FastAPI 线程池与 SQLite 线程检查冲突）
- [x] 状态覆盖：初始全量展示（无搜索词）、加载骨架屏、空结果、网络错误 Toast

**验收**：
- [x] `npm run dev` + `uv run uvicorn backend.main:app --reload` 同时启动，搜索全流程可用
- [x] 3 种断点（PC / 平板 / 手机）Masonry 布局正常
- [x] 空结果、网络错误 UI 已实现

---

### S3 · UC-02 详情 Modal + 端到端联调

**目标**：完成 DetailModal，与后端联调，确认完整用户流程可用、移动端适配正常。

- [ ] `DetailModal.tsx`：
  - 布局：PC 左图右文（左侧最大 58%）/ 移动端上图下文（图高 ≤ 60vh）
  - 大图 `object-contain`，黑色背景
  - title（等宽小字辅色）、tags（Badge 组件）、description（辅色小字）
  - 关闭：右上角 ×、ESC 键、点击遮罩（`#000000cc` + `backdrop-blur-sm`）
- [ ] 点击卡片时懒加载 `/api/items/{id}` 详情（不在 Masonry 预取）
- [ ] 端到端联调：UC-01 搜索 → 点击卡片 → UC-02 Modal 完整流程
- [ ] 移动端浏览器验证（iOS Safari / Chrome）

**验收**：
- [ ] 点击任意卡片 → Modal 弹出，大图/标签/描述与 DB 数据一致
- [ ] ×、ESC、遮罩三种关闭方式均正常
- [ ] 移动端上下布局正确，图片不溢出

---

### S4 · 部署 + CI/CD

**目标**：配置 Dockerfile 多阶段构建，完成 Fly.io 首次部署，建立自动化 CI/CD 流水线。

#### Dockerfile

```dockerfile
# Stage 1: 前端构建
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build          # 产物输出至 ../backend/static

# Stage 2: 后端运行时
FROM python:3.12-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
COPY --from=frontend-build /app/backend/static backend/static
CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] `fly.toml` 配置（对齐 Phase 03 S5 设计）：`primary_region = "hkg"`，persistent volume 挂载 `/data`
- [ ] 本地 `docker build && docker run` 验证可访问

#### Fly.io 首次部署

- [ ] 配置 Fly.io secrets：

  | 变量 | 说明 |
  |------|------|
  | `DATABASE_PATH` | `/data/tnjindex.db` |
  | `OSS_ENDPOINT` / `OSS_BUCKET` | 阿里云 OSS HK |
  | `OSS_ACCESS_KEY_ID` / `OSS_ACCESS_KEY_SECRET` | RAM 子账号（只读 OSS）|
  | `TNJ_EMBED_PROVIDER` / `TNJ_EMBED_MODEL` | Embedding 模型 |

- [ ] `fly deploy` 首次部署，公网 HTTPS URL 验证 UC-01/02 可用
- [ ] 将本地 `data/tnjindex.db` 上传至 persistent volume

#### CI/CD

```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build frontend
        run: cd frontend && npm ci && npm run build
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
```

- [ ] 配置 `FLY_API_TOKEN` GitHub secret
- [ ] push main 触发 workflow，验证 Actions 绿

**验收**：
- [ ] 公网 HTTPS URL 可访问，UC-01/02 功能完整
- [ ] push main 自动触发部署，Actions green
- [ ] 大陆网络下页面加载 ≤ 3s（首屏），搜索响应 ≤ 2s

---

## 验收标准（Phase 04 总体）

- [ ] 公开可访问的 HTTPS URL（Fly.io hkg 节点）
- [x] UC-01：自然语言搜索返回相关梗图，Masonry 布局正常，无限滚动可用（本地联调已验收，2026-04-12）
- [ ] UC-02：点击图片弹出 Modal，展示大图/标签/描述
- [x] 搜索质量：固定查询集 Top-5 主观满意（S2-v2 / `eval_memo.md` + 本地 UC-01 联调；公网环境 S4 后再检）
- [ ] push main 自动触发 CI/CD，部署成功
- [ ] 大陆网络环境下体验可接受

---

## 任务清单

- [x] S1 后端 API 搭建 + 搜索质量优化（核心三端点 + DB 依赖 + 语义 distance 阈值；`backend/static` 条件挂载 + CORS 已落地）
- [x] S2 前端搭建 + UC-01 搜索页（2026-04-12 验收）
- [ ] S3 UC-02 详情 Modal + 端到端联调
- [ ] S4 Dockerfile + Fly.io + CI/CD
- [x] 同步 `docs/mvp/00_roadmap.md` Phase 04 进度（S2 完成说明）
