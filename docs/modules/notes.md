# notes 模块卡

- **职责**:Markdown 笔记的创建、编辑、关联。不做:富文本(未来子类型)。
- **架构锚点**:§8.3
- **能力**(初始集):`create_note / update_note / delete_note(L2)/
  list_notes(摘要)/ get_note / link_note(关联资源与图谱节点)`
- **事件**:发布 `note.created / note.edited`
- **设置项**:`notes.editor.*`
- **数据**:笔记表,独立命名空间;list 只回摘要,正文按需(§9.20)
- **依赖**:platform
- **状态**:骨架
