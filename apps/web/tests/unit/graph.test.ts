/** 图谱页:store 两级加载合并去重、d3 数据派生、SSE 状态迁移。 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { deriveGraph, useGraphStore, type GraphEdge, type GraphNode } from '@/pages/graph/graphStore';

const callMock = vi.fn();

vi.mock('@/bridge/client', () => ({
  callCapability: (...args: unknown[]) => callMock(...args),
  ServiceError: class extends Error {
    code = '';
    hint = '';
  },
}));

function node(p: Partial<GraphNode> = {}): GraphNode {
  return {
    id: 'n1',
    label: 'Function',
    name: 'run',
    qualified_name: 'toy.main.run',
    attrs: {},
    source: 'code',
    actor: 'engine.python',
    ...p,
  };
}

function edge(p: Partial<GraphEdge> = {}): GraphEdge {
  return {
    id: 'e1',
    src: 'n1',
    dst: 'n2',
    type: 'CALLS',
    attrs: {},
    source: 'code',
    ...p,
  };
}

beforeEach(() => {
  callMock.mockReset();
  useGraphStore.setState({
    project: 'toy',
    projects: ['toy'],
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
  });
});

describe('deriveGraph 派生', () => {
  it('Map -> 渲染数组;悬空边被过滤', () => {
    const nodes = new Map([
      ['n1', node()],
      ['n2', node({ id: 'n2', name: 'go' })],
    ]);
    const edges = new Map([
      ['e1', edge()],
      ['e2', edge({ id: 'e2', src: 'n1', dst: 'ghost' })], // 端点不在画布
    ]);
    const { nodes: outNodes, links } = deriveGraph({ nodes, edges });
    expect(outNodes).toHaveLength(2);
    expect(links).toHaveLength(1);
    expect(links[0].source).toBe('n1');
    expect(links[0].target).toBe('n2');
  });
});

describe('graphStore 两级加载', () => {
  it('expand 合并去重:同一节点两次展开不产生重复', async () => {
    const a = node();
    const b = node({ id: 'n2', name: 'go', qualified_name: 'toy.helper.go' });
    callMock.mockResolvedValue({ nodes: [a, b], edges: [edge()] });
    await useGraphStore.getState().expand('n1');
    await useGraphStore.getState().expand('n1'); // expanded 集合挡掉,不再拉
    const s = useGraphStore.getState();
    expect(callMock).toHaveBeenCalledTimes(1);
    expect(s.nodes.size).toBe(2);
    expect(s.edges.size).toBe(1);
    expect(s.expanded.has('n1')).toBe(true);
  });

  it('expand 不同节点结果按 id 覆盖合并,重复节点不膨胀', async () => {
    const a = node();
    const b = node({ id: 'n2', name: 'go', qualified_name: 'toy.helper.go' });
    callMock.mockResolvedValueOnce({ nodes: [a, b], edges: [edge()] });
    await useGraphStore.getState().expand('n1');
    callMock.mockResolvedValueOnce({ nodes: [a, b], edges: [edge()] }); // 结果重叠
    await useGraphStore.getState().expand('n2');
    const s = useGraphStore.getState();
    expect(s.nodes.size).toBe(2); // 同 id 覆盖,不产生重复
    expect(s.edges.size).toBe(1);
  });

  it('reload 重置视图;stats 更新', async () => {
    callMock.mockImplementation((_d: string, name: string) => {
      if (name === 'graph_stats') return Promise.resolve({ total_nodes: 5, total_edges: 4 });
      if (name === 'query_graph') return Promise.resolve({ nodes: [node()], edges: [] });
      return Promise.resolve({});
    });
    await useGraphStore.getState().reload();
    await vi.waitFor(() => {
      expect(useGraphStore.getState().stats?.total_nodes).toBe(5);
    });
    expect(useGraphStore.getState().nodes.size).toBe(1);
  });

  it('searchLocate 高亮命中并选中第一个', async () => {
    const a = node();
    const b = node({ id: 'n2', name: 'runner' });
    callMock.mockImplementation((_d: string, name: string) => {
      if (name === 'graph_stats') return Promise.resolve({ total_nodes: 2, total_edges: 0 });
      return Promise.resolve({ nodes: [a, b], edges: [] });
    });
    useGraphStore.setState({ keyword: 'run' });
    await useGraphStore.getState().searchLocate();
    const s = useGraphStore.getState();
    expect(s.highlight.size).toBe(2); // run 与 runner 都命中
    expect(s.selected).toBeTruthy();
  });
});

describe('graphStore.dispatch 状态迁移', () => {
  it('task.completed 触发当前项目 reload', async () => {
    const spy = vi.fn().mockResolvedValue(undefined);
    useGraphStore.setState({ reload: spy } as never);
    useGraphStore.getState().dispatch({
      type: 'task.completed',
      payload: { project: 'toy', job_id: 'j1' },
    });
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('graph.engine.fallback -> 徽标显示 Python 回退', () => {
    useGraphStore.getState().dispatch({
      type: 'graph.engine.fallback',
      payload: { reason: 'C 引擎不可达' },
    });
    expect(useGraphStore.getState().engine).toEqual({
      engine: 'python',
      healthy: true,
      fallback: true,
    });
  });
});

describe('手建节点/边', () => {
  it('createNode 写入 Map 并选中;createEdge 返回边 id', async () => {
    const created = node({ id: 'n9', label: 'Concept', name: 'ReAct 模式',
                           qualified_name: 'ReAct 模式', source: 'manual', actor: '' });
    callMock.mockImplementation((_d: string, name: string, _args: Record<string, unknown>) => {
      if (name === 'set_node') return Promise.resolve(created);
      if (name === 'set_relationship') return Promise.resolve(edge({ id: 'e9', src: 'n1', dst: 'n9' }));
      if (name === 'get_subgraph') return Promise.resolve({ nodes: [created], edges: [] });
      return Promise.resolve({});
    });
    await useGraphStore.getState().createNode({ label: 'Concept', name: 'ReAct 模式' });
    expect(useGraphStore.getState().nodes.get('n9')?.name).toBe('ReAct 模式');
    expect(useGraphStore.getState().selected).toBe('n9');

    const eid = await useGraphStore.getState().createEdge({
      src: 'toy.main.run', dst: 'ReAct 模式', type: 'RELATES_TO',
    });
    expect(eid).toBe('e9');
    expect(useGraphStore.getState().edges.has('e9')).toBe(true);
  });
});
