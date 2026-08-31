/** 常驻悬浮对话窗(§10.12):圆点 ↔ 面板两态;与 chat 页同一 chatStore
 * 与 SSE 通道(两个视图共用 hooks/useChatStream:历史 + 上线 + 订阅);
 * 新消息到达且收起时圆点显示未读数;ask_user 弹窗复用;agent.navigate
 * 跳页后对话不中断。chat 路由时整个组件不渲染(主聊天就在那里)。
 */

import { useCallback, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { create } from 'zustand';
import { subscribe } from '@/bridge/stream';
import { useChatStore } from '@/stores/chatStore';
import { useChatStream } from '@/hooks/useChatStream';
import { useChatSend } from '@/hooks/useChatSend';
import { MessageList, ObserveLine, TaskCards } from '@/widgets/chat/MessageList';
import { ChatLlmMissingTip } from '@/widgets/chat/ChatLlmMissingTip';
import { AskDialog } from '@/widgets/chat/AskDialog';
import { ChatControls } from '@/widgets/chat/ChatControls';
import { NavIcons } from '@/components/icons/NavIcons';

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

export function FloatingChat() {
  const { open, unread, setOpen } = useFloatingStore();
  const navigate = useNavigate();
  const listRef = useRef<HTMLDivElement>(null);
  const messages = useChatStore((s) => s.messages);
  const connected = useChatStore((s) => s.connected);
  const { draft, setDraft, sending, llmMissing, send } = useChatSend();

  const onNavigate = useCallback(
    (path: string) => {
      navigate(path); // 跳页后悬浮窗仍在,对话不中断(§10.1)
    },
    [navigate],
  );
  useChatStream(onNavigate);

  useEffect(() => {
    return subscribe(['agent.message'], () => {
      if (!useFloatingStore.getState().open) {
        useFloatingStore.setState((s) => ({ unread: s.unread + 1 }));
      }
    });
  }, []);

  useEffect(() => {
    if (open && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [open, messages.length]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, setOpen]);

  if (!open) {
    return (
      <button
        type="button"
        className="float-dot"
        aria-label={unread > 0 ? `打开对话,未读 ${unread} 条` : '打开对话'}
        aria-expanded={false}
        onClick={() => setOpen(true)}
      >
        <NavIcons.chat width={22} height={22} />
        {unread > 0 ? <span className="float-dot__unread">{Math.min(unread, 99)}</span> : null}
      </button>
    );
  }

  return (
    <div className="float-panel">
      <div className="float-panel__head">
        <span className="float-panel__title">对话</span>
        <span className="small muted">
          {connected ? '在线' : '重连中…'}
        </span>
        <button type="button" className="btn btn-sm" onClick={() => setOpen(false)}>
          收起
        </button>
      </div>
      <ChatControls />
      <div className="float-panel__body" ref={listRef}>
        <MessageList />
        <TaskCards />
      </div>
      <ObserveLine />
      {llmMissing ? <ChatLlmMissingTip /> : null}
      <div className="float-panel__input">
        <textarea
          rows={2}
          value={draft}
          placeholder={llmMissing ? '先在设置里配置 LLM' : '就地聊一句…(Enter 发送)'}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <button
          type="button"
          className="btn btn-primary"
          disabled={sending || llmMissing || !draft.trim()}
          onClick={() => void send()}
        >
          发送
        </button>
      </div>
      <AskDialog />
    </div>
  );
}
