# services — 领域服务集群

每个目录 = 一个独立进程(§13.1):自带注册表 → REST + MCP,测试只跑自己目录。
新增领域 = 复制 `_template`,不触碰任何其他目录。

## 端口登记处(单一登记,新服务在此领号)

| 端口 | 服务 | 状态 |
|---|---|---|
| 8000 | gateway | 骨架 |
| 8010 | sources | 骨架 |
| 8020 | notes | 骨架 |
| 8030 | graph | 现有 services/graph_engine,迁移后领用 |
| 8040 | office | 骨架 |
| 8050 | code-exec | 骨架 |
| 8060 | browser | 骨架 |
| 8070 | llm | 骨架 |
| 8080 | settings | 骨架 |
| 8090 | _template | 示例 |

## 迁移说明(旧布局 → 目标布局)

- `services/api` → `services/gateway`(§6.3);
- `services/agent` → 顶层 `agent/`(§6.6);
- `services/graph_engine` → `services/graph`(§8.4);
- `services/mcp` → 能力由各服务自带 `mcp_server.py` 暴露,聚合挂载点归入 gateway。

迁移前旧目录照常工作;迁移是独立步骤,不在本次地基范围。
