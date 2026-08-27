/** 图谱页状态:两级加载(L0 概览 query / L1 双击展开 get_subgraph)。
 *
 * nodes/edges 用 Map 存,query 与 subgraph 结果都 merge 进去(按 id 去重);
 * d3 渲染数组从 Map 派生(deriveGraph)。SSE task.* 驱动索引进度,
 * task.completed 后自动刷新概览。
 */

import { create } from 'zustand';
import { callCapability, ServiceError } from '@/bridge/client';

export interface GraphNode {
  id: string;
  label: string;
  name: string;
  qualified_name: string;
  attrs: Record<string, unknown>;
  source: string; // manual | ai | code
  actor: string;
}

export interface GraphEdge {
  id: string;
  src: string;
  dst: string;
  type: string;
  attrs: Record<string, unknown>;
  source: string;
}

export interface IndexJob {
  id: string;
  project: string;
  repo_path: string;
  priority: number;
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled';
  attempts: number;
  error: string;
  created_ts: number;
  updated_ts: number;
}

export interface EngineState {
  engine: string; // c | python
  healthy: boolean;
  fallback: boolean; // 收到过 graph.engine.fallback 事件
}

/** L0 概览上限:后端默认 200;过滤/展开代替全量(坑 1)。 */
export const OVERVIEW_LIMIT = 500;
/** 大图告警阈值:L0 超过此数提示切 label 过滤(聚合视图留待 C 引擎)。 */
export const LARGE_GRAPH_WARN = 2000;

interface GraphState {
  project: string;
  projects: string[];
  keyword: string;
  label: string;
  nodes: Map<string, GraphNode>;
  edges: Map<string, GraphEdge>;
  expanded: Set<string>; // 已 L1 展开过的节点 id
  selected: string | null;
  highlight: Set<string>; // 搜索定位高亮
  stats: { total_nodes: number; total_edges: number } | null;
  loading: boolean;
  error: { code: string; message: string } | null;
  /** enqueue 表单可用的仓库清单(来自资源库,显示名 -> local_path) */
  repos: { name: string; local_path: string }[];
  init: () => Promise<void>;
  setProject: (project: string) => void;
  setFilter: (patch: { keyword?: string; label?: string }) => void;
  reload: () => Promise<void>;
  expand: (nodeId: string) => Promise<void>;
  select: (nodeId: string | null) => void;
  searchLocate: () => Promise<void>;
  createNode: (input: { label: string; name: string; qualified_name?: string }) => Promise<void>;
  createEdge: (input: { src: string; dst: string; type: string }) => Promise<string>;
  loadRepos: () => Promise<void>;
  /** SSE 事件(task.* / graph.engine.fallback);纯状态迁移,可单测。 */
  dispatch: (ev: { type: string; payload: Record<string, unknown> }) => void;
  /** 引擎徽标数据(懒探测,失败保持 unknown 不阻断页面) */
  engine: EngineState | null;
  refreshEngine: () => Promise<void>;
}

function mergeGraph(
  nodes: Map<string, GraphNode>,
  edges: Map<string, GraphEdge>,
  patch: { nodes?: GraphNode[]; edges?: GraphEdge[] },
): void {
  for (const n of patch.nodes ?? []) nodes.set(n.id, n);
  for (const e of patch.edges ?? []) edges.set(e.id, e);
}

export const useGraphStore = create<GraphState>((set, get) => ({
  project: '',
  projects: [],
  keyword: '',
  label: '',
  nodes: new Map(),
  edges: new Map(),
  expanded: new Set(),
  selected: null,
  highlight: new Set(),
  stats: null,
  loading: false,
  error: null,
  repos: [],
  engine: null,

  init: async () => {
    set({ loading: true, error: null });
    try {
      const projects = await callCapability<string[]>('graph', 'list_projects');
      const next = projects.includes(get().project) ? get().project : projects[0] ?? '';
      set({ projects, project: next });
      if (next) {
        await get().reload();
        void get().refreshEngine().catch(() => {
          // 徽标数据缺失不阻断画布
        });
      } else {
        set({ loading: false });
      }
    } catch (err) {
      const e = err as ServiceError;
      set({ loading: false, error: { code: e.code, message: e.message } });
    }
  },

  setProject: (project) => {
    set({ project, nodes: new Map(), edges: new Map(), expanded: new Set(),
          selected: null, highlight: new Set(), stats: null });
    void get().reload();
  },

  setFilter: (patch) => {
    set(patch);
    void get().reload();
  },

  reload: async () => {
    const { project, keyword, label } = get();
    if (!project) return;
    set({ loading: true });
    try {
      const g = await callCapability<{ nodes: GraphNode[]; edges: GraphEdge[] }>(
        'graph', 'query_graph',
        { project, keyword: keyword || undefined, label: label || undefined, limit: OVERVIEW_LIMIT },
      );
      // L0 重载替换视图:概览是当前镜头,展开结果不保留(重新双击即可)
      const nodes = new Map<string, GraphNode>();
      const edges = new Map<string, GraphEdge>();
      mergeGraph(nodes, edges, g);
      set({ nodes, edges, expanded: new Set(), loading: false });
      void callCapability<{ total_nodes: number; total_edges: number }>(
        'graph', 'graph_stats', { project },
      ).then((stats) => set({ stats })).catch(() => {
        // 统计失败不阻断
      });
    } catch (err) {
      const e = err as ServiceError;
      set({ loading: false, error: { code: e.code, message: e.message } });
    }
  },

  expand: async (nodeId) => {
    const { project, expanded } = get();
    if (!project || expanded.has(nodeId)) return;
    try {
      const sub = await callCapability<{ nodes: GraphNode[]; edges: GraphEdge[] }>(
        'graph', 'get_subgraph', { project, node_id: nodeId, depth: 1 },
      );
      const nodes = new Map(get().nodes);
      const edges = new Map(get().edges);
      mergeGraph(nodes, edges, sub); // 同 id 覆盖 = 去重
      set({ nodes, edges, expanded: new Set(expanded).add(nodeId) });
    } catch {
      // 展开失败保持现图(降级不惊扰)
    }
  },

  select: (nodeId) => set({ selected: nodeId, highlight: nodeId ? new Set([nodeId]) : new Set() }),

  searchLocate: async () => {
    await get().reload();
    const { keyword, nodes } = get();
    if (!keyword) {
      set({ highlight: new Set() });
      return;
    }
    const kw = keyword.toLowerCase();
    const hits = new Set(
      [...nodes.values()]
        .filter((n) => n.name.toLowerCase().includes(kw)
          || n.qualified_name.toLowerCase().includes(kw))
        .map((n) => n.id),
    );
    set({ highlight: hits });
    const first = hits.size > 0 ? [...hits][0] : null;
    if (first) set({ selected: first });
  },

  createNode: async (input) => {
    const { project } = get();
    const node = await callCapability<GraphNode>('graph', 'set_node', { project, ...input });
    const nodes = new Map(get().nodes);
    nodes.set(node.id, node);
    set({ nodes, selected: node.id });
  },

  createEdge: async (input) => {
    const { project } = get();
    const edge = await callCapability<GraphEdge>('graph', 'set_relationship', { project, ...input });
    // 端点可能是占位节点(服务端自动建):拉子图补全显示
    await get().expand(edge.src).catch(() => {});
    await get().expand(edge.dst).catch(() => {});
    const edges = new Map(get().edges);
    edges.set(edge.id, edge);
    set({ edges });
    return edge.id;
  },

  loadRepos: async () => {
    // 资源库已就绪的仓库(enqueue 表单的 project/repo_path 候选)
    const repos = await callCapability<
      { owner: string; name: string; local_path: string; status: string }[]
    >('sources', 'list_repos', {}).catch(() => []);
    set({
      repos: repos
        .filter((r) => r.status === 'ready' && r.local_path)
        .map((r) => ({ name: `${r.owner}/${r.name}`, local_path: r.local_path })),
    });
  },

  dispatch: (ev) => {
    const p = ev.payload;
    switch (ev.type) {
      case 'task.completed': {
        // 索引完成:当前项目相关则刷新概览
        if (p.project === get().project) void get().reload();
        break;
      }
      case 'graph.engine.fallback': {
        set({ engine: { engine: 'python', healthy: true, fallback: true } });
        break;
      }
      default:
        break;
    }
  },

  refreshEngine: async () => {
    const info = await callCapability<{ engine: string; healthy: boolean }>(
      'graph', 'engine_info', {},
    );
    set({ engine: { engine: info.engine, healthy: info.healthy,
                    fallback: get().engine?.fallback ?? info.engine === 'python' } });
  },
}));

/** d3 渲染数据派生:Map -> 数组,只保留两端都在画布上的边(可单测)。 */
export function deriveGraph(state: {
  nodes: Map<string, GraphNode>;
  edges: Map<string, GraphEdge>;
}): { nodes: GraphNode[]; links: { edge: GraphEdge; source: string; target: string }[] } {
  const nodes = [...state.nodes.values()];
  const ids = new Set(nodes.map((n) => n.id));
  const links = [...state.edges.values()]
    .filter((e) => ids.has(e.src) && ids.has(e.dst))
    .map((edge) => ({ edge, source: edge.src, target: edge.dst }));
  return { nodes, links };
}
