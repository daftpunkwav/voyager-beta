# graph 模块卡

- **职责**:知识图谱的构建、存储与查询。不做:内容理解(AI 管线由 agent 阅读内容后
  调写入原语,本服务不 directly 调 LLM)。
- **架构锚点**:§8.4(双管线、引擎适配层、L0/L1 分层)
- **分层(L0/L1)**:
  - **L0 = 跨资源关联层**:`universe` 命名空间。范围可选(kinds ⊆ repo/doc/web,
    可只分析代码仓库、只分析其他资源或任意组合)。当前由确定性 meta 管线
    (标签重合 → `RELATED` 边,source="meta")兜底;AI 管线的语义关联是叠加项
    (agent 经 set_node/set_relationship 写入,source="ai"),重建时保留。
    L1 产生的 `cross-repo` 依赖边并入 l0_view 输出。
  - **L1 = 单资源深度层**:code 仓库走程序化管线(C/Python 引擎解析,source="code");
    文档/网页等的 L1 由 AI 管线负责(agent 阅读内容后建图),引擎不参与。
- **能力**:

  队列与任务:
  - `enqueue_index(project, repo_path)` — L1 code 仓库索引入队(长任务,task.* 事件)
  - `enqueue_l0(kinds, priority)` — L0 跨资源关联分析入队(kinds 校验)
  - `cancel_index / reorder_queue / list_index_jobs` — 队列管理(index_jobs 带 level/kinds)

  写入原语(AI 管线):`set_node / set_relationship / set_nodes / set_relationships /
  merge_nodes / graph_guide`

  读取与规划:`l0_view(kinds, limit)` / `query_graph / get_subgraph / graph_stats /
  list_projects / engine_info / expand_neighbors / find_path / export_subgraph /
  drop_project_graph`
- **管线**:
  - `pipelines/code`(程序化):`analyze.py` 引擎解析 → 引擎id→规范id 映射 → 落库;
    `relate.py` 索引后自动跨仓关联(共享外部依赖 → CROSS_REPO 边,cross-repo 空间)。
  - `pipelines/l0`(程序化,确定性):`relate.py` 资源清单(经 wiring 注入的
    resource_provider 回调,deploy 装配时从 sources fan-out,graph 不 import sources)
    → Resource 节点 + 标签重合 RELATED 边;重建先 purge_meta(只清 meta 数据,
    保留 AI 产出);独立运行无 provider 时任务失败并提示需聚合形态。
  - `pipelines/ai`:guide 词表+校验;建图由 agent 执行(演进中)。
- **事件**:发布 `graph.indexed`、`task.progress/completed/failed`;订阅 `source.ready`
- **设置项**:`graph.engine`(auto|c|python,默认 auto)/ `graph.queue.concurrency`
- **数据**:节点/边/嵌入,独立命名空间(l0 用 `universe`,跨仓关联用 `cross-repo`);
  引擎:C sidecar 默认,Python 回退(决策 §15)
- **依赖**:platform;不依赖其他领域服务(sources 资源清单经装配根注入回调)
- **状态**:已实现(34 服务测试)。已落地:规范图存储(upsert,source/actor 区分)、
  引擎适配层(C 优先、健康失败回退 Python 并发 `graph.engine.fallback` 事件)、
  优先级索引队列(重试 backoff + 待命空转;level/kinds 分层)、code 管线、
  L0 meta 关联管线(l0_view/enqueue_l0)、AI 管线 guide。
  遗留:C sidecar 进程监督(自动拉起)未做,仅探测+回退;AI 语义关联管线
  (agent 建图)演进中;source.* 事件驱动的资源目录自动刷新未做
  (当前 L0 按需拉取快照);资源删除后 universe 中的孤立 AI 边由读取层悬空容忍。
