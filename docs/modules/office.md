# office 模块卡

- **职责**:办公文档(Word 类 doc / PPT 类 slides)的创建、编辑、导出。聚合服务,
  同 sources 模式:子模块脱耦,聚合层零逻辑(§8.6)。
- **架构锚点**:§8.6、§10.6(工坊)
- **能力**(初始集 → 规划):doc/slides 各自的 create/edit/export;编辑粒度到元素
  (配合工坊"鼠标指哪 agent 知道"的页面上报)
- **事件**:发布 `doc.created / doc.edited`
- **设置项**:`office.export.dir`(默认 workspace/exports/)
- **数据**:文档内容与版本,独立命名空间
- **依赖**:platform
- **状态**:骨架
