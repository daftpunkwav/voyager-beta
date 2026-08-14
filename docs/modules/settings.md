# settings 模块卡

- **职责**:应用级设置聚合:汇总各服务设置 schema,供设置页动态渲染(§10.11);
  自有 defs 三组——外观(主题/字号/代码字体)、交互(仲裁模式/安静时段/触达预算)、
  隐私(行为上报开关)。不做:具体设置项的业务消费(各项归所属服务)。
- **架构锚点**:§8.8、§7.9
- **能力**(已实现 6):`list_themes / get_theme / set_theme(cost 低,可静默)/
  get_settings(按 module 过滤的聚合 schema)/ get_setting / set_setting`;
  secret 项写保护由 platform SettingsStore 强制(非 user → SETTINGS.FORBIDDEN),
  secret 项读取只回 has_value 不回值
- **事件**:`settings.changed`(由 SettingsStore 在每次写入时发布,web 热切换)
- **设置项**:自身 `appearance.* / interaction.* / privacy.*`
- **数据**:经 platform/settings 存储
- **依赖**:platform
- **状态**:已实现(10 测试)
