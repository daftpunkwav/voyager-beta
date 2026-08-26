import type { AgentId } from '@/api/types';
import { AGENT_ROLE_LABELS } from '@/utils/labels';

/** 展示用：压空白、去掉无意义默认前缀 */
export function cleanSwitchReason(reason: string | undefined | null): string {
  const r = (reason ?? '').replace(/\s+/g, ' ').trim();
  if (!r || r.startsWith('Hub 调度')) return '';
  return r;
}

/**
 * 切换条副标题：优先短 reason，否则用角色标签。
 * 过长时在标点处截断，避免把模型长推理原文铺满聊天区。
 */
export function displaySwitchReason(
  reason: string | undefined | null,
  toAgent: string,
  limit = 72
): string {
  const role = AGENT_ROLE_LABELS[toAgent as AgentId] ?? '';
  const cleaned = cleanSwitchReason(reason);
  if (!cleaned) return role;
  if (cleaned.length <= limit) return cleaned;
  const cut = cleaned.slice(0, limit);
  const seps = ['。', '；', '！', '？', '，', ',', ';', ' '];
  let best = -1;
  for (const sep of seps) {
    const i = cut.lastIndexOf(sep);
    if (i >= Math.max(24, Math.floor(limit / 2))) {
      best = Math.max(best, i + (['。', '；', '！', '？'].includes(sep) ? 1 : 0));
    }
  }
  const clipped = (best > 0 ? cut.slice(0, best) : cut).replace(/[，,;；\s]+$/u, '');
  return `${clipped}…`;
}
