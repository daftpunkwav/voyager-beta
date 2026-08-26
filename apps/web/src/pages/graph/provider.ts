/** 图谱页 provider:对外暴露索引级摘要，不暴露 store 实现。 */

import type { PageProbe } from '@/bridge/pageContext';
import { useGraphStore } from './graphStore';

export const graphProvider: PageProbe = {
  page: 'graph',
  report() {
    const { project, nodes, edges, selected, stats, loading } = useGraphStore.getState();
    if (loading && nodes.size === 0) return null;
    const sel = selected ? nodes.get(selected)?.name ?? '' : '';
    const total = stats?.total_nodes ?? nodes.size;
    return {
      summary: `项目 ${project || '(未选)'}:${total} 节点 / ${stats?.total_edges ?? edges.size} 边`,
      counts: { loaded: nodes.size },
      selected: sel,
    };
  },
};
