import { create } from 'zustand';
import type { CodeGraphNode } from '@/components/code-graph/types';

interface CodeGraphState {
  nodeTypeFilter: Set<string> | null; // null = all
  edgeTypeFilter: Set<string> | null;
  showLabels: boolean;
  showOnlyDead: boolean;
  colorByStatus: boolean;
  hideTests: boolean;
  hideEntryPoints: boolean;
  nodeBudget: number;
  selectedNode: CodeGraphNode | null;
  searchQuery: string;
  viewMode: 'structure' | 'cluster' | 'trace';
  /** 左侧过滤栏是否收起 */
  leftPanelCollapsed: boolean;
  setNodeTypeFilter: (v: Set<string> | null) => void;
  toggleNodeType: (kind: string) => void;
  setEdgeTypeFilter: (v: Set<string> | null) => void;
  setShowLabels: (v: boolean) => void;
  setShowOnlyDead: (v: boolean) => void;
  setColorByStatus: (v: boolean) => void;
  setHideTests: (v: boolean) => void;
  setHideEntryPoints: (v: boolean) => void;
  setNodeBudget: (v: number) => void;
  selectNode: (n: CodeGraphNode | null) => void;
  setSearchQuery: (q: string) => void;
  setViewMode: (m: CodeGraphState['viewMode']) => void;
  setLeftPanelCollapsed: (collapsed: boolean) => void;
}

export const useCodeGraphStore = create<CodeGraphState>((set, get) => ({
  nodeTypeFilter: null,
  edgeTypeFilter: null,
  showLabels: false,
  showOnlyDead: false,
  colorByStatus: false,
  hideTests: false,
  hideEntryPoints: false,
  nodeBudget: 5000,
  selectedNode: null,
  searchQuery: '',
  viewMode: 'structure',
  leftPanelCollapsed: false,
  setNodeTypeFilter: (v) => set({ nodeTypeFilter: v }),
  toggleNodeType: (kind) => {
    const cur = get().nodeTypeFilter;
    if (!cur) {
      set({ nodeTypeFilter: new Set([kind]) });
      return;
    }
    const next = new Set(cur);
    if (next.has(kind)) next.delete(kind);
    else next.add(kind);
    set({ nodeTypeFilter: next.size ? next : null });
  },
  setEdgeTypeFilter: (v) => set({ edgeTypeFilter: v }),
  setShowLabels: (v) => set({ showLabels: v }),
  setShowOnlyDead: (v) => set({ showOnlyDead: v }),
  setColorByStatus: (v) => set({ colorByStatus: v }),
  setHideTests: (v) => set({ hideTests: v }),
  setHideEntryPoints: (v) => set({ hideEntryPoints: v }),
  setNodeBudget: (v) => set({ nodeBudget: v }),
  selectNode: (n) => set({ selectedNode: n }),
  setSearchQuery: (q) => set({ searchQuery: q }),
  setViewMode: (m) => set({ viewMode: m }),
  setLeftPanelCollapsed: (collapsed) => set({ leftPanelCollapsed: collapsed }),
}));
