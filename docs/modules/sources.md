# sources 模块卡

- **职责**:统一管理"可学习的资源"(仓库/书籍/新闻/未来类型)。聚合服务:
  聚合层零逻辑,只做注册表合并与类型分发;子模块间互不 import(§8.2)。
- **架构锚点**:§8.2
- **能力**(已实现 20,按子模块):
  - repo:`import_repo(长任务,git clone --depth 1 → workspace/repo/)/ list_repos(摘要,不回 readme)/
    sort_repos / get_repo / get_readme / set_repo_meta(分类+标签)/ list_categories /
    remove_repo(不可逆)/ search_remote_repos / list_starred_repos /
    set_github_token(仅 user)`
  - books:`add_book / list_books / get_chapter / remove_book`
  - news:`fetch_news / add_news / list_news / get_news / remove_news`
- **事件**:发布 `source.added / source.removed / source.ready / task.progress / task.failed`
- **设置项**:`sources.repo.clone_concurrency`、`sources.sort.default` 等
- **数据**:各子模块自己的表;资源本体落 workspace/{repo,books,news}/
- **依赖**:platform(github 客户端走 httpx)
- **状态**:已实现(12 测试;修订自旧 projects/categories/github 路由——
  category 字符串化、tags json 化、readme 导入时缓存)
