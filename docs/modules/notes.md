# notes 模块卡

- **职责**:Markdown 笔记的创建、编辑、关联。不做:富文本(未来子类型)。
- **架构锚点**:§8.3
- **能力**(已实现 6):`create_note / update_note / delete_note(不可逆)/
  list_notes(摘要,excerpt 120 字)/ get_note(按需全文)/ link_note(关联资源与图谱节点)`
- **事件**:发布 `note.created / note.edited / note.deleted`(修订:旧版无删除事件,
  活动页撤销需要)
- **设置项**:`notes.sort.default / notes.list.page_size / notes.editor.autosave_s`
- **数据**:笔记表,独立命名空间;list 只回摘要,正文按需(§9.20)
- **依赖**:platform
- **状态**:已实现(6 测试)
