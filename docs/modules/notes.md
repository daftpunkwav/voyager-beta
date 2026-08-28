# notes 模块卡

- **职责**:Markdown 笔记的创建、编辑、关联与附件图片。不做:富文本(未来子类型)。
- **架构锚点**:§8.3
- **能力**(已实现):`create_note / update_note / delete_note(软删入回收站)/
  list_notes(摘要,excerpt 120 字;state/sort/tag/query 过滤)/ get_note(按需全文)/
  link_note(关联资源与图谱节点)/ restore_note / purge_note(不可逆,连带清附件)/
  empty_trash / list_tags / rename_tag / get_backlinks / notes_stats /
  list_versions / read_version / restore_version(内容变更自动快照)/
  get_note_toc(跳过代码围栏)/ resolve_links([[内链]] 解析)/
  edit_note_range(字符偏移原子编辑)/ mark_note_span(选区底纹 ==tone:text==)/
  import_note(front-matter 导入)/
  export_note(front-matter 导出)/ add_asset(图片附件,attachment:// 引用,
  workspace/ 内 file_path、扩展白名单、notes.assets.max_mb 上限)/
  get_notes_view / set_notes_view(笔记页界面:字号/视图/布局/筛选/排序/回收站面板;
  assist 打开悬浮对话;quote 把选区交给讲解人格,均不落库。用户按钮与 agent 同权)`
- **事件**:发布 `note.created / note.edited / note.deleted / note.restored /
  note.purged / notes.ui.changed`
- **设置项**:`notes.sort.default / notes.list.page_size / notes.editor.autosave_s /
  notes.trash.retention_days / notes.history.per_note / notes.export.dir /
  notes.assets.max_mb / notes.ui.font_size / notes.ui.mode / notes.ui.layout /
  notes.ui.sync_scroll / notes.ui.list_state / notes.ui.sort / notes.ui.filter /
  notes.ui.query / notes.ui.source_id / notes.ui.panel / notes.ui.density`
- **数据**:notes.db(笔记/版本/双链)+ assets.db(note_assets)独立命名空间;
  附件文件落 workspace/notes-assets/<asset_id><ext>(内容寻址,永不覆盖,
  immutable 缓存路由 `GET /api/notes/assets/{id}`)
- **依赖**:platform
- **状态**:已实现 v0.5.0(registry 与 service.json 一致性有专项测试)
