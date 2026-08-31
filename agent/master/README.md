# agent/master — 主 agent(骨架)

统筹·仲裁·派单:master.py(用户对话/任务分解/监督/汇总入口)、arbiter.py(消息仲裁:
排队默认/自动/引导,§9.7)、digest.py(subagent 状态卡片,§9.6)、proactive.py(主动触达:
问候/追问/预算熔断,§9.8)、dispatch.py(派单装配与后台执行,§9.4)、observe.py(consider
观察留痕与自动索引,§9.2)。
