import { create } from 'zustand';

/** L0 图谱视图模式（展示形态） */
export type GraphViewMode = 'force' | 'list';

/** L0 力导向画布内的几何布局（对标原生引擎 力导向/树状/径向） */
export type GraphLayoutMode = 'force' | 'tree' | 'radial';

interface GraphState {
  selectedNodeId: string | null;
  highlightNodeId: string | null;
  searchQuery: string;
  minSimilarity: number;
  maxEdges: number;
  /** L0 资源种类筛选:null=全部;否则为选中的 kind 集合(repo/doc/web) */
  kindsFilter: Set<string> | null;
  /** L0 边类型:related | cross_repo | all */
  edgeTypeFilter: string | null;
  /** L0 视图模式 */
  viewMode: GraphViewMode;
  /** 力导向画布布局算法 */
  layoutMode: GraphLayoutMode;
  /** 左侧信息栏是否折叠 */
  leftPanelCollapsed: boolean;
  /** 节点详情面板是否折叠 */
  detailCollapsed: boolean;
  zoomLevel: number;
  zoomTick: number;
  zoomDirection: 'in' | 'out' | null;
  selectNode: (nodeId: string | null) => void;
  highlightNode: (nodeId: string | null) => void;
  setSearchQuery: (query: string) => void;
  setMinSimilarity: (value: number) => void;
  setMaxEdges: (value: number) => void;
  toggleKindFilter: (kind: string) => void;
  setKindsFilter: (kinds: Set<string> | null) => void;
  setEdgeTypeFilter: (edgeType: string | null) => void;
  setViewMode: (mode: GraphViewMode) => void;
  setLayoutMode: (mode: GraphLayoutMode) => void;
  setLeftPanelCollapsed: (collapsed: boolean) => void;
  setDetailCollapsed: (collapsed: boolean) => void;
  setZoomLevel: (level: number) => void;
  requestZoom: (direction: 'in' | 'out') => void;
  resetView: () => void;
}

export const useGraphStore = create<GraphState>((set) => ({
  selectedNodeId: null,
  highlightNodeId: null,
  searchQuery: '',
  minSimilarity: 0.08,
  /** 与 API Query le 对齐；过大会导致未热更后端时 422「参数校验失败」 */
  maxEdges: 1000,
  kindsFilter: null,
  edgeTypeFilter: null,
  viewMode: 'force',
  layoutMode: 'force',
  leftPanelCollapsed: false,
  detailCollapsed: false,
  zoomLevel: 1.0,
  zoomTick: 0,
  zoomDirection: null,

  selectNode: (nodeId) => set({ selectedNodeId: nodeId, detailCollapsed: false }),
  highlightNode: (nodeId) => set({ highlightNodeId: nodeId }),
  setSearchQuery: (query) => set({ searchQuery: query }),
  setMinSimilarity: (value) =>
    set({ minSimilarity: Math.max(0, Math.min(1, value)) }),
  setMaxEdges: (value) => set({ maxEdges: Math.max(10, Math.min(1000, value)) }),
  toggleKindFilter: (kind) =>
    set((state) => {
      const base = state.kindsFilter ?? new Set(['repo', 'doc', 'web']);
      const next = new Set(base);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      // 全选/全不选都回到 null(=全部),避免空集死图
      return { kindsFilter: next.size === 0 || next.size === 3 ? null : next };
    }),
  setKindsFilter: (kinds) => set({ kindsFilter: kinds }),
  setEdgeTypeFilter: (edgeType) => set({ edgeTypeFilter: edgeType }),
  setViewMode: (mode) => set({ viewMode: mode }),
  setLayoutMode: (mode) => set({ layoutMode: mode }),
  setLeftPanelCollapsed: (collapsed) => set({ leftPanelCollapsed: collapsed }),
  setDetailCollapsed: (collapsed) => set({ detailCollapsed: collapsed }),
  setZoomLevel: (level) => set({ zoomLevel: level }),
  requestZoom: (direction) =>
    set((state) => ({ zoomDirection: direction, zoomTick: state.zoomTick + 1 })),

  resetView: () =>
    set({
      selectedNodeId: null,
      highlightNodeId: null,
      searchQuery: '',
      zoomLevel: 1.0,
      layoutMode: 'force',
    }),
}));
