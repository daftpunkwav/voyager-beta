# Voyager

本地优先的 agent 共生工作台：导入仓库/文档/网页，笔记与知识图谱，人和 agent 走同一套 capability。

人格：常驻 orchestrator（显示名 Lucien）+ 4 个预设（侦察 / 讲解 / 整理 / 图谱向导）。品牌字符串只在仓库根 `brand.json`。

**技术栈：** FastAPI + sqlite3 / React + TypeScript + Vite。默认单体装配（`deploy/`）一进程跑 gateway + 领域服务 + agent；图谱 C 引擎可作为 sidecar。

## 快速开始

```bash
uv sync        # Python 依赖（uv workspace）
npm install    # Node 依赖（npm workspaces）
```

配置 `SECRETS_ENCRYPTION_KEY` 或 `SECRET_KEY`（随机长串，不要用 `.env.example` 里的示例值）后启动；在设置页填入 LLM API Key（BYOK）。无 Key 时对话降级，资料库/笔记/图谱仍可用。

### 开发启动

```bash
python deploy/dev.py    # gateway :8000 + Vite :5173
```

push / MR 由 GitLab CI 先 `ruff check agent deploy` 再跑默认 pytest（`.gitlab-ci.yml`），本地等价命令 `uv run ruff check agent deploy` 与 `uv run pytest -q`。

## 端口

| 服务 | 默认端口 | 覆盖变量 |
|------|----------|----------|
| Web（Vite dev） | 5173 | `VITE_PORT` |
| gateway（uvicorn） | 8000 | — |
| 图谱 C 引擎 sidecar | 8123 / 9750 | 见服务设置 |

完整环境变量清单见 `.env.example`。架构见 `docs/architecture.md`。

## 目录结构

```
├── apps/web/          # React 前端（只经 gateway）
├── agent/             # Agent runtime（独立包）
├── services/          # 领域服务：gateway / sources / notes / graph / llm / settings …
├── platform/          # 横切机制（contracts / capability / eventbus / …）
├── deploy/            # 单体装配与开发入口
├── brand.json         # 品牌字符串唯一来源
└── docs/architecture.md
```

工程规范见 `AGENTS.md`。
