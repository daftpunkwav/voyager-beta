# gateway 模块卡

- **职责**:apps 的唯一后端入口。不做:任何领域业务。
- **架构锚点**:§6.3、§7.10
- **能力**(初始集):路由聚合、令牌校验(§7.4)、SSE 汇聚(chat 通道 + 任务进度)、
  设置 schema 聚合读取、健康聚合探测(复用 platform/health)、AskUser 应答回投
- **事件**:订阅 `service.health.changed / agent.message / task.*`;转发给前端
- **设置项**:`gateway.rate_limit.*`(入口限流,§7.5)
- **数据**:无领域数据;本机令牌经 platform/actor
- **依赖**:platform + 各服务(反向依赖它们的 REST/MCP)
- **状态**:骨架
