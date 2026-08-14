# platform/audit — 审计(骨架)

一切变更类 capability 调用落审计:actor / capability / 输入摘要 / 结果 / ts / trace_id(§7.6)。

capability 框架已定义 `AuditSink` 协议与 `AuditEntry`(含入参脱敏);本包承接
**落库实现**(runtime-data/audit.db)与查询接口,活动页(§10.8)是其可视化。
