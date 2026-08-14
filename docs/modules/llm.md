# llm 模块卡

- **职责**:LLM 提供商目录、连接管理、用量计量出口。不做:提示词与决策(agent)。
- **架构锚点**:§8.8
- **能力**(初始集 → 规划):`list_providers / add_provider / test_connection /
  list_models / set_default`;常见提供商预置 base url 与模型目录;
  api key 为 secret——**只能用户本人写**(§8.8)
- **事件**:`settings.changed`(经 settings 框架)
- **设置项**:`llm.default_provider`、`llm.<name>.base_url / model / api_key(secret)`
- **数据**:提供商配置;密钥本体在 platform/secrets
- **依赖**:platform
- **状态**:骨架
