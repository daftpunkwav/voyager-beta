# llm 模块卡

- **职责**:LLM 提供商目录、连接管理、用量计量出口。不做:提示词与决策(agent)。
- **架构锚点**:§8.8
- **能力**(已实现 11):`list_builtin_providers / list_providers /
  get_provider_defaults / add_provider / update_provider / remove_provider /
  set_api_key(仅 user,_actor 注入强制)/ list_models / test_connection /
  complete(计量直写 usage)/ get_usage_stats`;
  内置 6 家常见提供商目录(base url、api_format=chat|anthropic、模型清单);
  `add_provider` 不接受 key 字段,key 走 platform/secrets(§8.8 secret 边界)
- **事件**:`settings.changed`(经 settings 框架)
- **设置项**:`llm.default_provider`、`llm.complete.*`
- **数据**:providers 与 usage 表(独立命名空间);密钥本体在 platform/secrets
- **依赖**:platform(httpx 直连出口,无 litellm)
- **状态**:已实现(7 测试,httpx.MockTransport mock 出口)
