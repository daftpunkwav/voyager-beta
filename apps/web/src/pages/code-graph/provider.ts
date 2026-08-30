/** 代码图谱详情页感知:至少报选中项目 id;节点/边未知时不算数字(null 不编造)。 */

import type { PageProbe } from '@/bridge/pageContext';

export interface CodeGraphSnapshot {
  projectId: string;
  /** null = 布局数据未就绪(不编数字) */
  nodes: number | null;
  edges: number | null;
}

let snapshot: CodeGraphSnapshot | null = null;

/** 项目 id 已知即写入;布局数据到达后更新计数。 */
export function rememberCodeGraphDetail(next: CodeGraphSnapshot | null): void {
  snapshot = next;
}

export function lastCodeGraphDetail(): CodeGraphSnapshot | null {
  return snapshot;
}

export const codeGraphProvider: PageProbe = {
  // 后端同属 graph 领域(报告的 page 字段仍是 graph)
  page: 'graph',
  report() {
    const s = snapshot;
    if (!s) return null;
    const countPart = s.nodes === null ? '' : ` · ${s.nodes} 节点 / ${s.edges ?? 0} 边`;
    const counts = s.nodes === null ? undefined : { nodes: s.nodes, edges: s.edges ?? 0 };
    return {
      summary: `代码图谱 · 项目 ${s.projectId}${countPart}`,
      counts,
      selected: s.projectId,
    };
  },
};
