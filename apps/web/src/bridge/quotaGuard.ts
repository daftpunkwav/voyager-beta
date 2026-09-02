/** Chat 发送前 token 日配额守卫(phase-67,§9.9)。
 *  后端 metered_llm 仍是权威拦截;本守卫只为更早反馈、省一轮无效请求。
 *  查询失败按软失败放行(不提示),由后端回复里的配额降级句兜底。 */

import { callCapability } from '@/bridge/client';

/** get_resource_quota 快照:当日用量与上限(0=不限) */
export interface QuotaSnapshot {
  tokens_used_today: number;
  daily_tokens: number;
}

export type QuotaGuardResult =
  | { action: 'allow' }
  | { action: 'warn'; ratio: number }
  | { action: 'block'; reason: string };

/** 发送前提醒阈值:≥80% 即 warn;用量页进度条的 0.9 是展示阈值,两者刻意不同 */
export const QUOTA_WARN_RATIO = 0.8;

export const QUOTA_BLOCK_MESSAGE = '今日 token 配额已用完，可在设置中调高或明日再试';

/** warn toast 文案(ratio 0-1) */
export function quotaWarnMessage(ratio: number): string {
  return `今日 token 配额已用 ${Math.round(ratio * 100)}%，发送可能很快触顶`;
}

/** 纯函数判定:limit≤0(不限) → allow;已满 → block;≥80% → warn;不依赖 React */
export function evaluateQuota(snapshot: QuotaSnapshot): QuotaGuardResult {
  const { tokens_used_today: used, daily_tokens: limit } = snapshot;
  if (!Number.isFinite(limit) || limit <= 0) return { action: 'allow' };
  if (used >= limit) return { action: 'block', reason: QUOTA_BLOCK_MESSAGE };
  const ratio = used / limit;
  if (ratio >= QUOTA_WARN_RATIO) return { action: 'warn', ratio };
  return { action: 'allow' };
}

/** 拉取配额并判定;查询失败软失败放行(后端 metered_llm 兜底) */
export async function fetchQuotaGuard(): Promise<QuotaGuardResult> {
  try {
    const snapshot = await callCapability<QuotaSnapshot>('agent', 'get_resource_quota', {});
    return evaluateQuota(snapshot);
  } catch {
    return { action: 'allow' };
  }
}
