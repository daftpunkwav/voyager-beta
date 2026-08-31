/** 团队页感知:人格 / 自建 subagent / 运行中实例的计数快照。
 *
 *  快照由各业务块 mount 成功后分字段 patch;三个字段都到达过才对外报告,
 *  避免谎报 0。加载失败不传 null,而是该字段未到达 → 整体仍 null。
 */

import type { PageProbe } from '@/bridge/pageContext';

export interface TeamSnapshot {
  personas: number;
  definitions: number;
  running: number;
}

/** 各字段是否至少 patch 过一次;三字段都到齐才报告。 */
interface PatchState {
  personas?: number;
  definitions?: number;
  running?: number;
}

const patched: PatchState = {};
let snapshot: TeamSnapshot | null = null;

function maybeCommit(): void {
  if (
    typeof patched.personas === 'number' &&
    typeof patched.definitions === 'number' &&
    typeof patched.running === 'number'
  ) {
    snapshot = {
      personas: patched.personas,
      definitions: patched.definitions,
      running: patched.running,
    };
  }
}

/** 分字段 patch;三字段都到齐后写入完整快照。 */
export function patchTeamSnapshot(next: Partial<TeamSnapshot>): void {
  if (typeof next.personas === 'number') patched.personas = next.personas;
  if (typeof next.definitions === 'number') patched.definitions = next.definitions;
  if (typeof next.running === 'number') patched.running = next.running;
  maybeCommit();
}

/** 直接写入完整快照(用于测试或需要强制覆盖的场景)。
 *  传 null 同时清掉分字段进度,避免下次单字段 patch 用残留值立刻提交。 */
export function rememberTeamSnapshot(next: TeamSnapshot | null): void {
  if (next === null) {
    snapshot = null;
    delete patched.personas;
    delete patched.definitions;
    delete patched.running;
    return;
  }
  patched.personas = next.personas;
  patched.definitions = next.definitions;
  patched.running = next.running;
  snapshot = { ...next };
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
