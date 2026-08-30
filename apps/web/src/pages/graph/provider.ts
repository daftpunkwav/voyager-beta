/** 图谱页(宇宙图)感知:节点/边计数 + 当前选中节点,不猜 cache 形状——
 *  useGraph 的 queryKey 含 filter,数量由 GraphPage 把当前视图的 nodes/edges
 *  长度写入本页 module cache(学 noteQuote.ts 先例),provider 只读。 */

import type { PageProbe } from '@/bridge/pageContext';

export interface GraphSnapshot {
  nodes: number;
  edges: number;
  selectedId: string;
  selectedName: string;
}

let snapshot: GraphSnapshot | null = null;

/** 数据到达时写入(传 null = 未就绪/离场,不报)。 */
export function rememberGraphSnapshot(next: GraphSnapshot | null): void {
  snapshot = next;
}

export function lastGraphSnapshot(): GraphSnapshot | null {
  return snapshot;
}

export const graphProvider: PageProbe = {
  page: 'graph',
  report() {
    const s = snapshot;
    if (!s) return null;
    const name = s.selectedName.trim().slice(0, 40);
    return {
      summary: `图谱 · ${s.nodes} 节点 / ${s.edges} 边${name ? ` · 选中 ${name}` : ''}`,
      counts: { nodes: s.nodes, edges: s.edges },
      selected: s.selectedId || undefined,
    };
  },
};
