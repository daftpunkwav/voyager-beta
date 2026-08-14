# graph 模块卡

- **职责**:知识图谱的构建、存储与查询。不做:内容理解(AI 管线由 agent 阅读内容后
  调写入原语,本服务不 directly 调 LLM)。
- **架构锚点**:§8.4(双管线、引擎适配层)
- **能力**:

  初始原语(已实现语义约定,未实现存储):
  - `enqueue_index / cancel_index / reorder_queue` — 索引任务队列管理
  - `set_node / set_relationship` — 基础写入原语(upsert 语义;用户手建、引擎解析、
    agent AI 建图同写一份图存储,来源字段区分 actor + pipeline)
  - `query_graph / get_subgraph` — 基础查询

  规划中的工具(在此演进,按需扩充):
  - 邻居展开 `expand_neighbors(node, depth, edge_filter)`
  - 路径查询 `find_path(a, b, max_hops)`
  - 批量操作 `set_nodes / set_relationships`(AI 管线减少往返)
  - 节点合并 `merge_nodes(a, b)`(去重)
  - 图统计 `graph_stats / degree_top`
  - 子图提取与导出 `export_subgraph(format)`
- **事件**:发布 `graph.indexed`、`task.progress/completed/failed`;订阅 `source.ready`
- **设置项**:`graph.engine`(auto|c|python,默认 auto)/ `graph.queue.concurrency`
- **数据**:节点/边/嵌入,独立命名空间;引擎:C sidecar 默认,Python 回退(决策 §15)
- **依赖**:platform;不依赖其他领域服务
- **状态**:骨架(现行为旧 services/graph_engine,待迁移)
