# agent/clients — 服务连接

- `pool.py`:外接 MCP server 连接池(§9.13/phase-11b)。用户在设置页添加
  stdio/URL 配置(`agent.mcp.servers`),连接并列出远端 tools;连接实现可注入,
  测试用 Fake。
- `mount.py`:把远端 tools 按 `mcp__<id>__<tool>` 挂进 Toolbelt;
  批准(整包/逐项)与移除卸载在此。
- `session.py`:MCP 会话产品路径(stdio 子进程 shell=False、HTTP POST JSON-RPC),
  最小握手 initialize → tools/list / tools/call。
- `discovery.py`:启动时按各服务 service.json 发现模块卡(只读卡,不连接)。

领域工具(notes__* 等)已走 deploy/bridge.py 的 capability 桥,
禁止再用 MCP client 把 services/*/mcp_server 灌进工具面。
