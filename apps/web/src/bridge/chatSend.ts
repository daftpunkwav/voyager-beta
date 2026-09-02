/** 聊天入队:POST /api/chat/messages。悬浮窗与笔记讲解共用,避免两套 fetch。 */

import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { useFloatingStore } from '@/widgets/FloatingChat';
import { fetchQuotaGuard, quotaWarnMessage } from '@/bridge/quotaGuard';

export async function postChatMessage(content: string): Promise<number> {
  const text = content.trim();
  if (!text) throw new Error('消息内容不能为空');
  const resp = await fetch('/api/chat/messages', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: text }),
  });
  const body = await resp.json().catch(() => null);
  if (resp.ok && body?.seq) return body.seq as number;
  throw new Error(`发送失败(${resp.status})`);
}

/** 任意页面把一句用户消息推进主时间线,并打开悬浮窗(当前已在 /chat 时悬浮窗不渲染)。
 *  发送前过同一份配额守卫:满配额抛错(调用方已有 catch + error toast);≥80% 提醒后照发。 */
export async function sendUserTurn(content: string): Promise<void> {
  const guard = await fetchQuotaGuard();
  if (guard.action === 'block') throw new Error(guard.reason);
  if (guard.action === 'warn') {
    useUIStore.getState().addToast({ type: 'warning', message: quotaWarnMessage(guard.ratio) });
  }
  const seq = await postChatMessage(content);
  useChatStore.getState().appendLocal({ seq, role: 'user', content: content.trim() });
  useFloatingStore.getState().setOpen(true);
}
