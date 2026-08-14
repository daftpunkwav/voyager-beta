# sources 模块卡

- **职责**:统一管理"可学习的资源"(仓库/书籍/新闻/未来类型)。聚合服务:
  聚合层零逻辑,只做注册表合并与类型分发;子模块间互不 import(§8.2)。
- **架构锚点**:§8.2
- **能力**(初始集,按子模块):
  - repo:`import_repo / list_repos / sort_repos / get_readme / remove_repo`
  - books:`add_book / get_chapter / list_books / remove_book`
  - news:`fetch_news / list_news / remove_news`
- **事件**:发布 `source.added / source.removed / source.ready`
- **设置项**:`sources.repo.clone_concurrency`、`sources.sort.default`……
- **数据**:各子模块自己的表;资源本体落 workspace/{repo,books,news}/
- **依赖**:platform
- **状态**:骨架
