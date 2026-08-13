# Voyager

AI 驱动的开源项目学习平台：导入/收藏 GitHub 项目，7 个 Agent（Hub 统筹 + Scout/Mentor/Navigator/Curator/Scribe/Atlas）辅助学习，知识图谱串联项目关联。

**技术栈：** FastAPI + SQLAlchemy + SQLite / React 19 + TypeScript + Vite 7。后端与 Agent 默认同进程（两进程），可拆分为独立进程（四进程）。

## 快速开始

```bash
uv sync        # Python 依赖（uv workspace）
npm install    # Node 依赖（npm workspaces）
```

配置 `SECRET_KEY`（≥32 字节，见 `.env.example`）后启动；在设置页填入 LLM API Key（BYOK）启用完整 Agent 能力，无 Key 时自动降级为规则/图谱模式。

### 一键开发（Windows）

```powershell
.\scripts\dev.ps1       # 两进程：API + Web
.\scripts\dev.ps1 -All  # 四进程：+ 独立 Agent（:19877）+ 图谱 sidecar（:9750）
```

图谱 sidecar 优先使用 C 引擎（`graph-engine`），未构建时回退 Python `graph_fallback`（装即用）。

## 端口

| 服务 | 默认端口 | 覆盖变量 |
|------|----------|----------|
| Web（Vite dev） | 5173 | `VITE_PORT` |
| API（uvicorn） | 19878 | `API_PORT` |
| Agent Runtime | 19877 | `AGENT_PORT` |
| 图谱引擎 sidecar | 9750 | `GRAPH_ENGINE_PORT` |

完整环境变量清单见 `.env.example`。

## 目录结构

```
voyager/
├── apps/web/          # React 前端
├── services/
│   ├── api/           # FastAPI 后端
│   ├── agent/         # Agent（agent_core + agent_runtime）
│   ├── graph_engine/  # 图谱（C 引擎 + Python 回退）
│   └── mcp/           # MCP Server（规划中）
├── packages/          # 共享库
├── scripts/           # 开发/构建脚本
└── tests/
```

工程规范与开发约定见 `AGENTS.md` / `CLAUDE.md`。
