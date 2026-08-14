/** 事件类型常量:与后端 platform_contracts.DomainEvent 对齐(§7.2)。 */

export const EventType = {
  /** 用户发往 agent 的消息(经 gateway chat 投递) */
  USER_MESSAGE: 'user.message',
  /** agent 回复 */
  AGENT_MESSAGE: 'agent.message',
  /** agent 需要用户交互(弹窗/选择/确认) */
  AGENT_ASK: 'agent.ask',
  /** agent 要求前端跳转 */
  AGENT_NAVIGATE: 'agent.navigate',
  /** 服务健康状态迁移(徽章条数据源) */
  SERVICE_HEALTH_CHANGED: 'service.health.changed',
  /** 任务生命周期(长任务进度) */
  TASK_COMPLETED: 'task.completed',
} as const;

export type EventTypeValue = (typeof EventType)[keyof typeof EventType];
