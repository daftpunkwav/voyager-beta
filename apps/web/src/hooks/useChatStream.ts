/** 聊天流接线(对话主页与常驻悬浮窗共用):历史加载 → 上线事件 → SSE 订阅。
 *
 * 断线续传由 bridge/stream 承担;历史走 GET /api/chat/messages
 * (user.message + agent.message,单时间线,gateway 不建会话表 §6.3);
 * POST /api/user/online 触发 agent 主动问候预算(services/gateway/activity.py)。
 */

import { useEffect } from 'react';
import { subscribe } from '@/bridge/stream';
import { safeInternalPath } from '@/utils/safeUrl';
import { type ChatEvent, useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';

const STREAM_PATTERNS = [
  'agent.message',
  'agent.ask',
  'agent.navigate',
  'agent.step',
  'agent.observe',
  'agent.policy.notify',
  'task.*',
  'note.created',
];

export function useChatStream(onNavigate: (path: string) => void) {
  useEffect(() => {
    const store = useChatStore.getState();
    // 历史重建;不可达不阻塞聊天,消息流从当前开始
    fetch('/api/chat/messages?after_seq=0&limit=200', { credentials: 'include' })
      .then((r) => r.json())
      .then((body) => store.applyHistory((body.messages ?? []) as ChatEvent[]))
      .catch(() => {});
    // 上线事件;失败静默(仅影响主动问候预算)
    fetch('/api/user/online', { method: 'POST', credentials: 'include' }).catch(() => {});

    const off = subscribe(STREAM_PATTERNS, (ev) => {
      if (ev.type === 'agent.navigate') {
        const path = safeInternalPath(ev.payload.path);
        if (path) onNavigate(path);
        return;
      }
      if (ev.type === 'agent.policy.notify') {
        // L1 权限提示(§9.9):只弹 info toast,不进聊天时间线
        const msg = String(ev.payload?.message ?? '').trim();
        if (msg) useUIStore.getState().addToast({ type: 'info', message: msg });
        return;
      }
      useChatStore.getState().dispatch(ev as ChatEvent);
    });
    useChatStore.getState().setConnected(true);

    return () => {
      off();
      useChatStore.getState().setConnected(false);
    };
  }, [onNavigate]);
}
