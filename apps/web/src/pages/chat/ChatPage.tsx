/** 对话主页:单时间线(gateway 不建会话表,§6.3)。
 *
 * GET /api/chat/messages 重建历史;POST 经 useChatSend 发送;
 * SSE 经 hooks/useChatStream 订阅;与常驻悬浮窗共用同一 chatStore(§10.12)。
 * 行为迁自 apps/web/archived/chat/ChatPage.tsx(旧多会话 AgentPage 已下线)。
 */

import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useChatStore } from '@/stores/chatStore';
import { useChatStream } from '@/hooks/useChatStream';
import { useChatSend } from '@/hooks/useChatSend';
import { MessageList, ObserveLine, StepLine, TaskCards } from '@/widgets/chat/MessageList';
import { ChatLlmMissingTip } from '@/widgets/chat/ChatLlmMissingTip';
import { AskDialog } from '@/widgets/chat/AskDialog';
import { ChatControls } from '@/widgets/chat/ChatControls';

export function ChatPage() {
  const navigate = useNavigate();
  const connected = useChatStore((s) => s.connected);
  const { draft, setDraft, sending, llmMissing, send } = useChatSend();

  const onNavigate = useCallback(
    (path: string) => {
      navigate(path);
    },
    [navigate],
  );
  useChatStream(onNavigate);

  return (
    <section className="chat-page">
      <div className="chat-topbar">
        <ChatControls />
        <div className="chat-status small muted">
          {connected ? '已连接' : '连接断开,重连中…'}
        </div>
      </div>
      <MessageList />
      <TaskCards />
      <StepLine />
      <ObserveLine />
      {llmMissing ? <ChatLlmMissingTip /> : null}
      <div className="chat-input">
        <textarea
          rows={2}
          value={draft}
          placeholder={llmMissing ? '先在设置里配置 LLM' : '说点什么…(Enter 发送,Shift+Enter 换行)'}
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
    </section>
  );
}
