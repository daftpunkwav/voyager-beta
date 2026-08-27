# sources 模块卡

- **职责**:统一管理"可学习的资源"(仓库/文档/网页/未来类型)。聚合服务:
  聚合层零类型逻辑,只做注册表合并、跨类型 fan-out 与类型分发;子模块间互不
  import(§8.2)。
- **架构锚点**:§8.2
- **能力**(已实现 27,按子模块):
  - repo:`import_repo(长任务,git clone --depth 1 → workspace/repo/)/ list_repos(摘要,不回 readme)/
    sort_repos / get_repo / get_readme / set_repo_meta(分类+标签+进度+备注)/ list_categories /
    remove_repo(不可逆,发 source.removed;本地克隆由 worker 异步清理)/ search_remote_repos /
    list_starred_repos / set_github_token(仅 user)`
  - doc:`add_document(长任务;PDF/EPUB/DOCX/TXT/MD 分章解析,其他格式存档语义 stored)/
    list_documents(摘要)/ get_document(含分章大纲,不含正文)/ get_doc_section(按需取一章全文,§9.20)/
    search_documents(分章正文检索,带章号+片段)/ set_document_meta / remove_document(不可逆)`
  - web:`save_url(抓取网页正文,解析-钉住式 SSRF 防护)/ add_page(手动录入)/ list_pages /
    get_page / set_page_meta / remove_page(不可逆)`
  - 聚合:`list_sources(跨类型统一资源流,kind/status/tag/query 过滤+排序)/
    search_sources(标题/标签命中 + doc 分章正文命中带 section_no)/ sources_stats(各类型计数)`
- **事件**:发布 `source.added / source.removed / source.ready / task.progress / task.failed`;
  payload 统一含 `source_id` 与 `kind`(repo/doc/web)
- **设置项**:`sources.sort.default`、`sources.import.clone`、`sources.doc.max_file_mb`
- **数据**:各子模块自己的 sqlite(repo.db/doc.db/web.db);文档原文件落 workspace/doc/,
  网页正文入库;附件式只读路由 `GET /api/sources/files/doc/{id}`
- **依赖**:platform(github/httpx/pypdfium2/python-docx;EPUB 走标准库)
- **状态**:已实现 v0.2.0(43 测试;books→doc、news→web 一次性迁移已内置,
  旧库自动改名 *.bak)
