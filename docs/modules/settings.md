# settings 模块卡

- **职责**:应用级设置聚合:汇总各服务设置 schema,供设置页动态渲染(§10.11)。
  不做:具体设置项的业务消费(各项归所属服务)。
- **架构锚点**:§8.8、§7.9
- **能力**(初始集):`list_settings_schema / get_setting / set_setting`
  (secret 项经 platform/secrets 且仅 user 可写)
- **事件**:转发 `settings.changed`
- **设置项**:自身 `settings.ui.*`
- **数据**:经 platform/settings 存储
- **依赖**:platform
- **状态**:骨架
