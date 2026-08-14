/** Agent Chat 主页:与常驻 agent 对话,领域能力经 bridge 由 agent 侧调用。 */

import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useChatStore } from './chatStore';
import { useChatStream } from './useChatStream';
import { MessageList, TaskCards } from './MessageList';

export function ChatPage() {
  const navigate = useNavigate();
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const connected = useChatStore((s) => s.connected);

  // navigate 指令:agent 带用户跳页(useCallback 稳定引用,避免订阅重建)
  const onNavigate = useCallback(
    (path: string) => {
      navigate(path);
    },
    [navigate],
  );
  useChatStream(onNavigate);

  const send = async () => {
    const content = draft.trim();
    if (!content || sending) return;
    setSending(true);
    setDraft('');
    const fail = (text: string) => {
      const store = useChatStore.getState();
      store.appendLocal({ seq: -Date.now(), role: 'system', content: text });
      useChatStore.setState({ thinking: false });
    };
    try {
      const resp = await fetch('/api/chat/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      });
      const body = await resp.json().catch(() => null);
      if (resp.ok && body?.seq) {
        // user.message 不在 SSE 流类型内,本地按响应 seq 回显
        useChatStore.getState().appendLocal({ seq: body.seq, role: 'user', content });
      } else {
        fail(`发送失败(${resp.status})`);
      }
    } catch {
      fail('发送失败:后端不可达');
    } finally {
      setSending(false);
    }
  };

  return (
    <section className="chat-page">
      <div className="chat-status small muted">
        {connected ? '已连接' : '连接断开,重连中…'}
      </div>
      <MessageList />
      <TaskCards />
      <div className="chat-input">
        <textarea
          rows={2}
          value={draft}
          placeholder="说点什么…(Enter 发送,Shift+Enter 换行)"
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
    </section>
  );
}
