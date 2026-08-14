/** 聊天流接线:历史加载 → 上线事件 → SSE 订阅(断线续传由 bridge/stream 承担)。 */

import { useEffect } from 'react';
import { subscribe } from '@/bridge/stream';
import { type ChatEvent, useChatStore } from './chatStore';

const STREAM_PATTERNS = [
  'agent.message',
  'agent.ask',
  'agent.navigate',
  'task.*',
  'note.created',
];

export function useChatStream(onNavigate: (path: string) => void) {
  useEffect(() => {
    const store = useChatStore.getState();
    // 历史(事件日志重建):user.message + agent.message
    fetch('/api/chat/messages?after_seq=0&limit=200')
      .then((r) => r.json())
      .then((body) => store.applyHistory((body.messages ?? []) as ChatEvent[]))
      .catch(() => {
        // 历史不可达不阻塞聊天,消息流从当前开始
      });
    // 上线(触发 agent 主动问候预算,§9.8)
    fetch('/api/user/online', { method: 'POST' }).catch(() => {});

    const off = subscribe(STREAM_PATTERNS, (ev) => {
      if (ev.type === 'agent.navigate') {
        const path = String(ev.payload.path ?? '');
        if (path) onNavigate(path);
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
