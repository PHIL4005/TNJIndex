# Phase 03 — 产品设计

> 状态: **已完成** | 依赖: Phase 02 ✅；S1–S5 已定稿，`tech_design §5` 与 OSS 迁移已落地  
> 目标: 锁定网站架构、UI/UX 交互方案与迁移计划，产出可直接进入 Phase 04 开发的设计文档。

---

## 功能范围

| 功能 | 描述 | 优先级 |
|------|------|--------|
| **技术栈定稿** | 修订 `tech_design §5`（大陆可用优先的供应商替换） | P0 |
| **图片迁移** | 本地 → 阿里云 OSS 香港节点，DB URL 全量更新 | P0 |
| **UC-01 自然语言搜索** | 搜索框、Masonry 结果网格、加载/空/错误态 | P0 |
| **UC-02 素材详情** | Modal 大图 + 标签 + 描述 | P0 |
| **UC-03 标签筛选** | 标签多选 + 与搜索词组合 | P1 |
| **UC-04 素材复用** | 复制图片链接 + Toast 反馈 | P1 |
| **前端技术准备** | 组件库选型、项目结构、FastAPI serve 静态资源方案 | P0 |
| **部署与 CI/CD** | Fly.io `sin` 配置规划、GitHub Actions workflow | P0 |

**不在范围：** 实际代码开发（Phase 04）；再次扩量爬虫；用户账号系统。

---

## 步骤总览

| # | 步骤 | 核心产出 | 验收标志 |
|---|------|---------|---------|
| S1 | 技术栈定稿 | 更新 `tech_design §5` | 文档无遗留决策项 |
| S2 | 图片迁移 | OSS HK bucket 就绪 + DB URL 全量更新 | 随机 10 张图大陆可直接访问 |
| S3 | UX/交互设计 | 各 UC 设计草稿（见本文档） | UC-01/02 可直接指导 Phase 04 编码 |
| S4 | 前端技术准备 | 组件库选型 + 项目结构规划 | Phase 04 可直接初始化项目 |
| S5 | 部署与 CI/CD 规划 | Fly.io 配置方案 + Actions workflow 草稿 | Phase 04 可按方案直接操作，无需再做决策 |

---

## S1 · 技术栈定稿

**目标**：修订 `tech_design §5`，替换对中国大陆用户不友好的供应商。

**修订摘要**（详见 `tech_design §5`）：

| 层 | 原方案 | 修订后 | 原因 |
|----|--------|--------|------|
| 图片存储 | Cloudflare R2 | **阿里云 OSS 香港节点** | R2 无 CDN，大陆直连慢；OSS HK 延迟低 |
| 前端托管 | Vercel | **FastAPI `StaticFiles` serve 前端产物** | Vercel 大陆访问不稳定；合并到同一 app 简化部署 |
| 后端部署 | Fly.io（区域未指定） | **Fly.io `sin` region** | Fly 已不再提供 `hkg`；新加坡节点大陆延迟通常可接受（因线路而异） |
| CI/CD | Vercel 自动 + GitHub Actions | **GitHub Actions 统一** | 前后端合并后无需双平台 |

**任务**：
- [x] 按以上修订更新 `tech_design §5` 技术栈表、架构图、部署流程
- [x] 在 `tech_design §5` 候选方案对比区归档旧决策

**验收**：
- [x] `tech_design §5` 内容与本文档 S1 结论完全一致，无遗留"待决定"

---

## S2 · 图片迁移

**目标**：将本地 `data/images/originals/` 与 `thumbnails/` 迁移至阿里云 OSS 香港节点，更新 DB 中所有 `image_path` / `thumbnail_path` 为公开 URL。

**任务**：

- [x] 阿里云 OSS：创建 Bucket（区域：`oss-cn-hongkong`），设置**公共读**权限，配置 CORS（允许后续前端域名访问）
- [x] 编写迁移脚本 `pipelines/migrate_to_oss.py`：
  - 遍历 `data/images/originals/` + `thumbnails/`，上传到 OSS
  - 路径结构保持 `originals/{filename}` / `thumbnails/{filename}`
  - 上传成功后更新 DB 对应字段为 `https://{bucket}.oss-cn-hongkong.aliyuncs.com/{path}`
  - 支持幂等（已上传且 URL 已写入 DB 的跳过）
- [x] 验证：随机抽取 10 条记录，`curl` 检查 URL 返回 200 且图片可渲染

**验收**：
- [x] DB 中所有 Item 的 `image_path` / `thumbnail_path` 均为 OSS 公开 URL，无本地路径残留
- [x] 随机 10 张缩略图 URL，大陆网络环境下可正常访问（≤ 3s）
- [x] OSS Bucket 已配置 CORS，允许前端域名跨域读取图片

---

## S3 · UX/交互设计

### 视觉风格

**定位**：深色极简 · 工具感——梗图在深色背景上更突显，减少视觉噪音，突出图片本身。

**色彩**：

| 角色 | 色值 | 用途 |
|------|------|------|
| 页面背景 | `#0f0f0f` | 整体底色 |
| 表面（卡片/面板/Modal） | `#1c1c1e` | 次级层次 |
| 描边 / 分隔线 | `#2c2c2e` | 低噪音分隔 |
| 强调色 | `#f97316`（橙） | 按钮、标签高亮、链接；呼应 T&J 经典橙红 |
| 文字主色 | `#f4f4f5` | 正文、标题 |
| 文字辅色 | `#71717a` | 元数据、描述次要信息 |

**字体**：系统默认 sans-serif 栈（`-apple-system, 'PingFang SC', sans-serif`），不引入额外字重，确保中文渲染自然。

**卡片**：圆角 `rounded-xl`（12px），无明显边框；hover 时 `scale-[1.02]` + 橙色细边框出现，过渡约 150ms。

**参考**：[Frinkiac](https://frinkiac.com) 深色整体风格 + [Cat Meme Multiverse](https://cats.mixedbread.com) 搜索交互布局。

---

### UC-01 · 自然语言搜索（主页）

**页面结构**：

```
┌──────────────────────────────────────────────────────┐
│  TNJIndex                               [GitHub ↗]  │  ← 顶部导航，高度 48px，极简
├──────────────────────────────────────────────────────┤
│                                                      │
│         找到你想要的汤姆与杰瑞梗图                  │  ← Hero 区，居中，h2
│                                                      │
│  ┌────────────────────────────────────┐  [ 搜索 ]  │  ← 宽度 max-w-xl，Enter 或按钮触发
│  │  描述你想找的画面或情绪…           │            │
│  └────────────────────────────────────┘            │
│                                                      │
│  [嫌弃] [假笑] [被迫营业] [无语] [装死] …          │  ← 热门标签（按频次取前 8），点击直接搜索
│                                                      │
├──────────────────────────────────────────────────────┤
│  全部素材（500+）                  [标签筛选 ▾]     │  ← 结果区 header；无搜索词时展示全部
│                                                      │
│  ┌──────┐  ┌────┐  ┌───────┐  ┌────┐              │
│  │      │  │    │  │       │  │    │  ← Masonry    │
│  └──────┘  │    │  └───────┘  │    │    瀑布流     │
│  ┌────┐    │    │  ┌────┐     └────┘    PC: 4列    │
│  │    │    └────┘  │    │              平板: 2列    │
│  └────┘            └────┘              手机: 1列    │
│                                                      │
│              ↓ 无限滚动加载下一批                   │
└──────────────────────────────────────────────────────┘
```

**交互细节**：
- 搜索框 placeholder 每次页面加载随机换一条示例（如「一脸嫌弃」「被催婚时的心情」「假装没听见」）
- 搜索触发：按 Enter 或点击按钮；**不做 debounce 实时搜索**（每次需调 embedding API）
- 有搜索词时，结果区 header 变为「"xxx" 的搜索结果（N 条）」

**状态设计**：

| 状态 | 呈现方式 |
|------|---------|
| 初始（无查询） | 展示全部素材 Masonry，按 `created_at` 倒序 |
| 加载中 | 卡片位置显示骨架屏（`Skeleton`），搜索按钮出现 spinner |
| 空结果 | 居中插画区 + 「没找到相关梗图，换个描述试试？」+ 热门标签推荐 |
| 网络错误 | Toast 提示「搜索出错，请稍后重试」，不清空已有结果 |

---

### UC-02 · 素材详情（Modal）

**触发**：点击 Masonry 中任意图片卡片。

**Modal 结构**：

```
┌──────────────────────────────────────────────────────┐
│  [×]                                                 │  ← 右上角关闭；ESC 亦可
│                                                      │
│  ┌─────────────────────┐  ┌──────────────────────┐  │
│  │                     │  │ tom_pretending_dead  │  │  ← title，等宽小字（辅色）
│  │       大图           │  │                      │  │
│  │   （原图尺寸，        │  │  [装死][假装][嫌弃]  │  │  ← tags，Badge 组件，可点击
│  │    object-contain） │  │  [配合][逃避]         │  │    跳转至标签筛选
│  │                     │  │                      │  │
│  └─────────────────────┘  │  汤姆假装没听见杰瑞  │  │  ← description（辅色小字）
│                            │  说话，翻个白眼继续  │  │
│                            │  躺着…               │  │
│                            │                      │  │
│                            │  [复制图片链接]       │  │  ← UC-04 入口，橙色主按钮
│                            │  [查看原图 ↗]        │  │  ← 新标签打开 OSS 原图 URL
│                            └──────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

**布局规则**：
- PC：左图右文，左侧最大宽度 58%，图片 `object-contain`，背景 `#000`
- 移动端：上图下文，垂直排列；图片高度限 60vh
- Modal 遮罩：`#000000cc` + `backdrop-blur-sm`；点击遮罩关闭
- 上下翻页（可选 P2）：键盘 `←` / `→` 切换同搜索结果的前后一张

---

### UC-03 · 标签筛选（P1）

**触发**：点击结果区 header 右侧「标签筛选 ▾」。

**呈现**：Popover 面板，展示所有标签（按出现频次排序，超过 50 个则支持面板内搜索），每个标签旁显示计数。

**交互**：
- 多选后点「应用」：将选中标签加入查询条件（与搜索词 AND 组合）
- 已选标签在搜索框下方以橙色 chip 呈现，chip 上有 `×` 可单独删除
- 标签筛选与自然语言搜索可同时生效（后端 `/search` 支持 `tags` 参数）

---

### UC-04 · 素材复用（P1）

**入口一**：Masonry 卡片 hover 时，右下角浮现复制图标按钮（`16px`，`#f97316`）  
**入口二**：UC-02 详情 Modal 内「复制图片链接」主按钮

**行为**：
- 复制内容：该素材**缩略图**的 OSS 公开 URL（直接可粘贴到社区帖子/即时通讯）
- 反馈：`Toast` 通知「链接已复制 ✓」，2s 后消失
- 降级：`navigator.clipboard` 不可用时，fallback 到 `execCommand('copy')` 并提示「请手动复制」

---

## S4 · 前端技术准备

### 组件库选型

**选定：shadcn/ui + Tailwind CSS v4**

| 维度 | 说明 |
|------|------|
| 样式定制 | 可组合、无样式锁定；深色主题由 `class="dark"` 控制，开箱即用 |
| 体积 | 按需引入，tree-shaking 友好，bundle 小 |
| AI 辅助质量 | 代码生成工具对 shadcn 支持最好，Phase 04 加速明显 |
| 深色主题 | 原生支持，直接映射上文色彩方案 |

Masonry 布局：`react-masonry-css`（轻量，响应式断点配置简单）

### 项目目录规划

```
frontend/
├── src/
│   ├── components/
│   │   ├── SearchBar.tsx       # 搜索框 + 触发逻辑
│   │   ├── MasonryGrid.tsx     # 瀑布流容器 + 无限滚动
│   │   ├── ImageCard.tsx       # 单张卡片（hover 复制）
│   │   ├── DetailModal.tsx     # UC-02 Modal
│   │   └── TagFilter.tsx       # UC-03 Popover 面板
│   ├── hooks/
│   │   ├── useSearch.ts        # 封装 /api/search 调用与状态
│   │   └── useInfiniteScroll.ts
│   ├── lib/
│   │   └── api.ts              # API base URL、fetch 封装、类型定义
│   └── App.tsx
├── public/
├── index.html
└── vite.config.ts              # build.outDir = "../backend/static"
```

### FastAPI serve 静态资源

```python
# backend/main.py（示意）
from fastapi.staticfiles import StaticFiles

# API 路由统一加 /api 前缀，避免与前端路由冲突
app.include_router(api_router, prefix="/api")

# 最后 mount 静态目录（顺序重要：API 路由须先注册）
app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

`vite.config.ts` 设 `build.outDir: "../backend/static"`；CI 中先 build 前端，再 `fly deploy`。

---

## S5 · 部署与 CI/CD 规划

### Fly.io 配置要点

```toml
# fly.toml（关键字段）
app = "tnjindex"
primary_region = "sin"          # 新加坡；Fly 已不再提供 hkg，volume 须同区

[build]
  dockerfile = "Dockerfile"

[mounts]
  source = "tnjindex_data"
  destination = "/data"         # SQLite 文件挂载点；persistent volume

[[services]]
  internal_port = 8000
  protocol = "tcp"
  [[services.ports]]
    port = 443
    handlers = ["tls", "http"]
  [[services.ports]]
    port = 80
    handlers = ["http"]
```

**Dockerfile 结构思路**：
1. 多阶段构建：Stage 1 Node.js build 前端，Stage 2 Python/uv 安装后端依赖
2. 将 Stage 1 产物 `COPY` 到 `backend/static/`
3. `CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]`

### GitHub Actions Workflow

```yaml
# .github/workflows/deploy.yml（结构示意）
name: Deploy
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: prod   # 使用 GitHub Environment「prod」中的 Secrets（如 FLY_API_TOKEN）
    steps:
      - uses: actions/checkout@v4

      - name: Build frontend
        run: |
          cd frontend
          npm ci
          npm run build          # 产物输出到 backend/static/

      - name: Deploy to Fly.io
        uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
```

`--remote-only`：在 Fly.io 远端构建镜像，CI runner 无需安装 Docker。

### 环境变量（Fly.io secrets）

| 变量 | 说明 |
|------|------|
| `DATABASE_PATH` | `/data/tnjindex.db`（persistent volume 挂载路径） |
| `ALIYUN_OSS_ENDPOINT` | `https://oss-cn-hongkong.aliyuncs.com` |
| `ALIYUN_OSS_BUCKET_NAME` | Bucket 名 |
| `ALIYUN_OSS_ACCESS_KEY_ID` / `ALIYUN_OSS_ACCESS_KEY_SECRET` | 阿里云 RAM 子账号 AccessKey（只读 OSS 权限即可） |
| `ALIYUN_OSS_REGION` | 可选；默认 `oss-cn-hongkong`（与公开 URL 域名一致） |
| `TNJ_VISION_PROVIDER` / `TNJ_VISION_MODEL` | Phase 02 复用 |
| `TNJ_EMBED_PROVIDER` / `TNJ_EMBED_MODEL` | Phase 02 复用 |

---

## 验收标准

- [x] S1：`tech_design §5` 已按修订内容更新，架构图/技术栈表/部署流程与本文档 S1 结论一致
- [x] S2：全库 `image_path` / `thumbnail_path` 均为 OSS HK 公开 URL；随机 10 张大陆可访问
- [x] S3：UC-01 / UC-02 设计草稿完整（见本文档），可直接指导 Phase 04 编码；UC-03 / UC-04 草稿已记录
- [x] S4：组件库选型有据可查；项目目录结构已规划
- [x] S5：Fly.io 配置要点与 CI/CD workflow 草稿已写入本文档

---

## 任务清单

- [x] S1 修订 `docs/architecture/tech_design.md §5`
- [x] S2 创建阿里云 OSS Bucket + 编写 `pipelines/migrate_to_oss.py` + 验证 URL
- [x] S3 UX 草稿已在本文档 ✅（可直接进入 Phase 04）
- [x] S4 前端项目结构规划已在本文档 ✅（Phase 04 按此初始化）
- [x] S5 部署与 CI/CD 规划已在本文档 ✅（Phase 04 按此配置）
- [x] 更新 `docs/mvp/00_roadmap.md` Phase 03 状态为「已完成」
