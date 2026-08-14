# platform 模块卡

- **职责**:横切设施——机制层,唯一天然被所有模块依赖。不做:任何业务,
  不出现领域词汇与品牌名(§7)。
- **架构锚点**:§7 全章
- **子包与状态**:
  - ✅ contracts(纯类型:事件/DTO/错误码/协议版本)
  - ✅ actor(本机令牌、ActorContext)
  - ✅ eventbus(SQLite 追加日志 + 直推订阅 + 游标)
  - ✅ capability(定义/注册/守卫:鉴权 LocalAuth、配额 CostQuota、审计 sink;
    gen_rest / gen_mcp 双生成)
  - ✅ settings(SettingDef/SettingsStore:校验、secret 写保护、变更事件)
  - ✅ health(HealthMonitor、unavailable/queue_full 错误助手)
  - 骨架:limit(入口限流)/ audit(落库)/ observability / config / secrets
- **测试**:`pytest platform`(76 项)
- **依赖**:子包间单向 contracts ← 其余;capability → actor;settings/health → eventbus
- **状态**:地基已完成(§14 第 1 步的 platform 部分)
