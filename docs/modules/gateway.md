# gateway 模块卡

- **职责**:apps 的唯一后端入口。不做:任何领域业务(零业务数据,§6.3)。
- **架构锚点**:§6.3、§7.10
- **能力**(已实现):无自有注册表——聚合即全部:
  - REST 聚合:挂载清单(MountSpec)由部署入口注入,各服务注册表 →
    `/api/<domain>/capabilities/*`;ServiceError → 统一错误体(§7.10)
  - chat 通道:`POST /api/chat/messages` 投递 user.message;
    `GET /api/chat/messages` 从事件日志重建单时间线历史(修订:废弃旧多会话表);
    `GET /api/chat/stream` SSE 回推(agent.message/agent.ask/agent.navigate/task.*),
    支持 after_seq 断线续传、掉队从日志补齐、once 一次性追平模式
  - 行为上报:`POST /api/activity`(类别白名单)、`POST /api/user/online`;
    `GET /api/activity/feed` 活动页数据源
  - 健康聚合:`GET /health` 探测全部挂载服务,状态迁移发 service.health.changed
  - AskUser 应答:经挂载的 agent 注册表 `answer_question` 能力,无专用端点
  - 入口限流:每 actor 每分钟滑动窗口 + SSE 连接数上限(§7.5 第一层)
- **事件**:发布 `user.message / user.activity / user.online / service.health.changed`
- **设置项**:`gateway.rate_limit.per_minute / gateway.sse.max_connections /
  gateway.chat.history_page_size`(值由部署入口从共享 SettingsStore 注入)
- **数据**:仅内存限流计数与健康快照
- **依赖**:platform;不 import 任何领域服务(挂载由部署入口装配)
- **状态**:已实现(11 测试)
