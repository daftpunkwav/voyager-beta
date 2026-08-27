import { useQuery } from '@tanstack/react-query';
import { getApi } from '@/api/client';
import type { GraphData, GraphEdge, GraphNode } from '@/api/types';
import { useGraphStore } from '@/stores/graphStore';

/** 后端 l0_view 行形状(store 行;attrs 已是对象) */
interface L0NodeRow {
  id: string;
  label: string;
  name: string;
  qualified_name: string;
  attrs: {
    kind?: string;
    tags?: string[];
    category?: string;
    status?: string;
    subtitle?: string;
  };
}

interface L0EdgeRow {
  id?: string;
  src: string;
  dst: string;
  type: string;
  attrs: Record<string, unknown>;
}

interface L0View {
  nodes: L0NodeRow[];
  edges: L0EdgeRow[];
  cross_edges: L0EdgeRow[];
}

/** RELATED 权重归一:共享 1 个标签≈0.34,≥3 个封顶 1 */
function relatedWeight(shared: unknown): number {
  const n = Array.isArray(shared) ? shared.length : 1;
  return Math.min(1, n / 3);
}

/** 后端 L0 行 → 展示图数据(节点元数据入 GraphNode 扩展字段) */
function toGraphData(view: L0View): GraphData {
  const nodes: GraphNode[] = view.nodes.map((n) => ({
    id: n.id,
    name: n.name,
    stars: 0,
    kind: (n.attrs.kind as GraphNode['kind']) ?? undefined,
    tags: n.attrs.tags ?? [],
    category: n.attrs.category ?? '',
    status: n.attrs.status ?? '',
    description: n.attrs.subtitle ?? '',
    /** qualified_name = "{kind}:{资源id}",供跳转资源详情 */
    resourceId: n.qualified_name.includes(':')
      ? n.qualified_name.split(':').slice(1).join(':')
      : n.qualified_name,
  }));
  const edges: GraphEdge[] = [
    ...view.edges.map((e) => ({
      source: e.src,
      target: e.dst,
      similarity: relatedWeight(e.attrs.shared_tags),
      edge_type: e.type.toLowerCase(),
    })),
    ...view.cross_edges.map((e) => ({
      source: e.src,
      target: e.dst,
      similarity: 1,
      edge_type: e.type.toLowerCase(),
    })),
  ];
  return { nodes, edges };
}

/** L0 宇宙图数据源:graph.l0_view(kinds 由 store 决定) */
export function useGraph() {
  const kindsFilter = useGraphStore((s) => s.kindsFilter);
  const maxEdges = useGraphStore((s) => s.maxEdges);
  const kinds = kindsFilter ? [...kindsFilter] : undefined;

  return useQuery({
    queryKey: ['graph-l0', kinds, maxEdges],
    queryFn: async () => {
      const res = await getApi().getGraph({ kinds, limit: maxEdges });
      return toGraphData((res.data ?? { nodes: [], edges: [], cross_edges: [] }) as L0View);
    },
  });
}
