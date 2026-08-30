/** 团队页感知:人格 / 自建 subagent / 运行中实例的计数快照。
 *  数据在 TeamPage 组件 useState 里,provider 读不到 → 学 noteQuote.ts 的
 *  module cache 先例:由 TeamPage 在 list_personas / list_subagents 成功后写入;
 *  加载失败保持 null,不报「0 个人格」的谎言。 */

import type { PageProbe } from '@/bridge/pageContext';

export interface TeamSnapshot {
  personas: number;
  definitions: number;
  running: number;
}

let snapshot: TeamSnapshot | null = null;

/** 数据到达时写入;传 null 表示加载失败/离场,保持不报。 */
export function rememberTeamSnapshot(next: TeamSnapshot | null): void {
  snapshot = next;
}

export function lastTeamSnapshot(): TeamSnapshot | null {
  return snapshot;
}

export const teamProvider: PageProbe = {
  page: 'team',
  report() {
    const s = snapshot;
    if (!s) return null;
    return {
      summary: `团队 · ${s.personas} 个人格 · ${s.definitions} 个自建 · ${s.running} 个运行中`,
      counts: { personas: s.personas, definitions: s.definitions, running: s.running },
    };
  },
};
