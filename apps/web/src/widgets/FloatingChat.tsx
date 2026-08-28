/** 常驻悬浮对话窗(§10.12):圆点 ↔ 面板两态;与 chat 页同一 chatStore
 * 与 SSE 通道(两个视图);新消息到达且收起时圆点显示未读数;
 * ask_user 弹窗复用;agent.navigate 跳页后对话不中断。
 * chat 路由时整个组件不渲染(主聊天就在那里)。
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { create } from 'zustand';
import { subscribe } from '@/bridge/stream';
import { useChatStore } from '@/stores/chatStore';
import { MessageList, TaskCards } from '@/widgets/chat/MessageList';
import { AskDialog } from '@/widgets/chat/AskDialog';

interface FloatingState {
  open: boolean;
  unread: number;
  setOpen: (v: boolean) => void;
}

export const useFloatingStore = create<FloatingState>((set, get) => ({
  open: false,
  unread: 0,
  setOpen: (v) => set({ open: v, unread: v ? 0 : get().unread }),
}));

/** 悬浮窗自己的 SSE 接线(chat 页卸载后由它接管;同 store 两视图)。 */
function useFloatingStream(onNavigate: (path: string) => void, active: boolean) {
  useEffect(() => {
    if (!active) return;
    const patterns = [
      'agent.message', 'agent.ask', 'agent.navigate', 'task.*', 'note.created',
    ];
    return subscribe(patterns, (ev) => {
      if (ev.type === 'agent.navigate') {
        const path = String(ev.payload.path ?? '');
        if (path) onNavigate(path);
        return;
      }
      const store = useChatStore.getState();
      store.dispatch(ev);
      if (ev.type === 'agent.message' && !useFloatingStore.getState().open) {
        useFloatingStore.setState((s) => ({ unread: s.unread + 1 }));
      }
    });
  }, [onNavigate, active]);
}

export function FloatingChat() {
  const { open, unread, setOpen } = useFloatingStore();
  const navigate = useNavigate();
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const messages = useChatStore((s) => s.messages);

  const onNavigate = useCallback(
    (path: string) => {
      navigate(path); // 跳页后悬浮窗仍在,对话不中断(§10.1)
    },
    [navigate],
  );
  useFloatingStream(onNavigate, true);

  // 打开时滚到底;新消息时若已打开也滚底(两边滚动位置各自独立,坑 3:
  // 悬浮窗列表是独立容器,不与 chat 页共享 DOM)
  useEffect(() => {
    if (open && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [open, messages.length]);

  const send = async () => {
    const content = draft.trim();
    if (!content || sending) return;
    setSending(true);
    setDraft('');
    try {
      // §4.2.16 流式通道:chat send 当前走直接 fetch(后端 chat 入队端点),
      // 原因:callCapability 是 RPC 形态,而 chat 是流式双向协议
      // (POST 入队 + EventSource 推回)。后续 bridge/stream 抽象支持 streaming
      // 后,改为 callCapability('chat', 'send_message', { content }) 形式。
      const resp = await fetch('/api/chat/messages', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      });
      const body = await resp.json().catch(() => null);
      if (resp.ok && body?.seq) {
        useChatStore.getState().appendLocal({ seq: body.seq, role: 'user', content });
      } else {
        useChatStore.getState().appendLocal({
          seq: -Date.now(), role: 'system', content: `发送失败(${resp.status})`,
        });
      }
    } catch {
      useChatStore.getState().appendLocal({
        seq: -Date.now(), role: 'system', content: '发送失败:后端不可达',
      });
    } finally {
      setSending(false);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        className="float-dot"
        aria-label={`打开对话(未读 ${unread})`}
        onClick={() => setOpen(true)}
      >
        {unread > 0 ? <span className="float-dot__unread">{Math.min(unread, 99)}</span> : null}
      </button>
    );
  }

  return (
    <div className="float-panel">
      <div className="float-panel__head">
        <span className="float-panel__title">对话</span>
        <span className="small muted">
          {useChatStore.getState().connected ? '在线' : '重连中…'}
        </span>
        <button type="button" className="btn btn-sm" onClick={() => setOpen(false)}>
          收起
        </button>
      </div>
      <div className="float-panel__body" ref={listRef}>
        <MessageList />
        <TaskCards />
      </div>
      <div className="float-panel__input">
        <textarea
          rows={2}
          value={draft}
          placeholder="就地聊一句…(Enter 发送)"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <button type="button" className="btn btn-primary" disabled={sending || !draft.trim()}>
          发送
        </button>
      </div>
      <AskDialog />
    </div>
  );
}
