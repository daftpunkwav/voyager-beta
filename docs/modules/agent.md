# agent 模块卡

- **职责**:系统的决策者;常驻 runtime,与用户同权消费一切(隐私除外)。不做:
  业务数据存储(在各领域服务)。
- **架构锚点**:§9 全章(§9.1 十二职责 / §9.2 结构 / §9.4 subagent / §9.9 权限 /
  §9.20 按需加载)
- **能力**(agent 自身暴露,与用户同权,§5 agent/capabilities.py):
  读/改 agent 设置、查记忆、查任务、查 subagent 状态……初始集,按 §9 演进
- **事件**:发布 `agent.message / agent.navigate`;订阅 `user.message / user.online /
  user.activity / task.* / source.ready / service.health.changed / settings.changed /
  schedule.tick`
- **设置项**:`agent.rounds.max`、`agent.rounds.tool_max`、`agent.arbiter.mode`、
  `agent.proactive.*`(预算/安静时段)、`agent.style`、权限四维、工作目录……(§8.8)
- **数据**:runtime-data/memory、checkpoints;workspace/ 为默认工作目录
- **依赖**:platform + 各服务 MCP/REST(经 clients/ 服务发现)
- **状态**:已实现(§14 第 2、3 步):runtime 底座、master 统筹/仲裁/触达、
  subagent 七模式、四维权限、四类记忆、上下文装配、skills/hooks、8 个 parity 能力;
  170 测试全绿。clients/ 服务发现与各服务迁移属后续步骤
