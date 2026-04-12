# Phase 04 — MVP 开发与上线

> 状态: **规划中** | 依赖: Phase 03 ✅（含 OSS 图片迁移）  
> 目标: 按 Phase 03 设计完成 UC-01/02 并部署上线；UC-03/04（P1）完成后追加。

---

## 功能范围

| 功能 | 优先级 | 说明 |
|------|--------|------|
| Backend API（3 端点） | P0 | `/api/search`、`/api/items/{id}`、`/api/tags` |
| 搜索质量优化 | P0 | ⚠️ 当前检索效果差强人意，S1 中先诊断优化，再开前端 |
| 前端 UC-01 自然语言搜索 | P0 | 搜索框 + Masonry + 无限滚动 + 全状态覆盖 |
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

- [ ] 创建 `backend/` 模块，`main.py` 配置：
  - `/api` 路由前缀（须在 StaticFiles 之前注册）
  - `StaticFiles(directory="backend/static", html=True)` mount 到 `/`
  - CORS 中间件（开发阶段允许 localhost:5173）
- [ ] `deps.py`：`get_db()` 依赖，返回 sqlite-vec 已加载的 `sqlite3.Connection`
- [ ] `schemas.py`：定义响应模型
  - `ItemSummary`（id, title, thumbnail_path, tags）
  - `ItemDetail`（id, title, image_path, thumbnail_path, tags, description）
  - `TagCount`（name, count）
- [ ] `routers/search.py`：`GET /api/search?q=&tags=&limit=&offset=`，调用（优化后的）`pipelines/search.py`
- [ ] `routers/items.py`：`GET /api/items/{id}`
- [ ] `routers/tags.py`：`GET /api/tags`，按出现频次排序
- [ ] 废弃 `pipelines/app.py`

#### ⚠️ 搜索质量诊断与优化

> 当前 `pipelines/search.py` 已实现 sqlite-vec KNN，但在实际查询中效果差强人意。  
> S1 开始前须先定位根因，再决定"修补"还是"重写"。

可能原因（需逐一排查）：

| 方向 | 具体问题 |
|------|---------|
| 查询预处理 | 中文 query 直接 embed，与索引时的"中英混合 description+tags"存在语言分布偏差 |
| 向量相似度 | sqlite-vec 默认距离度量是否与 embedding 模型匹配（L2 vs cosine）|
| 召回策略 | 仅纯向量检索，无关键词兜底；少见标签或精确词无法命中 |
| top-k | 固定 k=10 可能过少，分页场景需支持更大 offset |

诊断方式：用 `pipelines/eval_queries.txt` 固定查询集跑当前结果，人工标注相关性，再对比改动后结果。

- [ ] 诊断：固定查询集跑当前检索，记录各条 Top-5 结果质量
- [ ] 根据诊断结论，选择以下一项或组合：
  - query 预处理（中文扩写 or 翻译为英文 + 中文）
  - 改用 cosine 距离（重建 `item_embeddings` 或修改查询）
  - 加入关键词混合检索（SQLite FTS5 或标签精确匹配兜底）
- [ ] 优化后重跑固定查询集，对比前后结果

**验收**：
- [ ] `uvicorn backend.main:app --reload` 本地启动无报错
- [ ] curl 3 个端点返回符合 schema 的 JSON
- [ ] 固定查询集 Top-5 主观满意，相比优化前有明显提升

---

### S2 · 前端搭建 + UC-01 搜索页

**目标**：初始化 React/Vite 项目，配置设计系统，完成搜索主页全部交互与状态。

#### 项目初始化

- [ ] `frontend/` 初始化（`npm create vite@latest` React + TypeScript）
- [ ] 安装依赖：shadcn/ui、Tailwind CSS v4、`react-masonry-css`
- [ ] 配置 Tailwind 色彩 token（深色主题，对齐 Phase 03 S3 色彩方案）：

  | Token | 值 | 用途 |
  |-------|----|------|
  | `background` | `#0f0f0f` | 页面底色 |
  | `surface` | `#1c1c1e` | 卡片/面板/Modal |
  | `border` | `#2c2c2e` | 描边/分隔线 |
  | `accent` | `#f97316` | 按钮/标签高亮/链接 |
  | `foreground` | `#f4f4f5` | 正文/标题 |
  | `muted` | `#71717a` | 元数据/次要信息 |

- [ ] `vite.config.ts`：`build.outDir: "../backend/static"`；开发代理 `/api` → `localhost:8000`
- [ ] `lib/api.ts`：fetch 封装，类型定义对齐 backend schemas

#### UC-01 实现

- [ ] `SearchBar.tsx`：搜索框 + Enter/按钮触发；placeholder 随机轮换示例短语
- [ ] `ImageCard.tsx`：缩略图卡片；hover `scale-[1.02]` + 橙色细边框，过渡 150ms
- [ ] `MasonryGrid.tsx`：瀑布流（PC 4列 / 平板 2列 / 手机 1列）
- [ ] `useSearch.ts`：搜索状态管理（loading / data / error / empty）
- [ ] `useInfiniteScroll.ts`：IntersectionObserver 触底加载下一页
- [ ] 热门标签区：调用 `/api/tags` 取前 8，点击直接触发搜索
- [ ] 状态覆盖：初始全量展示（无搜索词）、加载骨架屏、空结果、网络错误 Toast

**验收**：
- [ ] `npm run dev` + `uvicorn backend.main:app --reload` 同时启动，搜索全流程可用
- [ ] 3 种断点（PC / 平板 / 手机）Masonry 布局正常
- [ ] 空结果、网络错误 UI 已实现

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
- [ ] UC-01：自然语言搜索返回相关梗图，Masonry 布局正常，无限滚动可用
- [ ] UC-02：点击图片弹出 Modal，展示大图/标签/描述
- [ ] 搜索质量：固定查询集 Top-5 主观满意
- [ ] push main 自动触发 CI/CD，部署成功
- [ ] 大陆网络环境下体验可接受

---

## 任务清单

- [ ] S1 后端 API 搭建 + 搜索质量优化
- [ ] S2 前端搭建 + UC-01 搜索页
- [ ] S3 UC-02 详情 Modal + 端到端联调
- [ ] S4 Dockerfile + Fly.io + CI/CD
- [ ] 更新 `docs/mvp/00_roadmap.md` Phase 04 状态为「进行中」
