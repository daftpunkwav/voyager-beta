/** 主页 — Agent Chat(单时间线,常驻对话)。
 *
 * 入口点:与常驻悬浮窗(FloatingChat)共用同一 chatStore / 事件流。
 * 本页为独立模式:全宽单栏,无侧栏,适合"专注对话"。
 * SSE 接入走 bridge/stream.ts(共享 EventSource,after_seq 续传)。
 */

import { useEffect, useState } from 'react';
import { ChatPanel } from '@/components/agent/ChatPanel';
import { AgentContextSidebar } from '@/components/agent/AgentContextSidebar';
import { ConfirmDialog } from '@/widgets/ConfirmDialog';
import { useAgentStore } from '@/stores/agentStore';
import { LoadingSpinner } from '@/widgets/LoadingSpinner';
import { GlassCard } from '@/widgets/GlassCard';

export function ChatPage() {
  const loadSessions = useAgentStore((s) => s.loadSessions);
  const sessions = useAgentStore((s) => s.sessions);
  const currentSessionId = useAgentStore((s) => s.currentSessionId);
  const error = useAgentStore((s) => s.error);
  const [showSidebar, setShowSidebar] = useState(true);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  return (
    <div className="chat-page glass-card liquid-glass--panel">
      <header className="chat-page__head">
        <h1 className="h2">对话</h1>
        <button
          type="button"
          className="btn btn-text btn-sm"
          onClick={() => setShowSidebar((v) => !v)}
        >
          {showSidebar ? '收起侧栏' : '展开侧栏'}
        </button>
      </header>
      {error ? (
        <GlassCard className="chat-page__error">
          <p className="text-error">{error}</p>
        </GlassCard>
      ) : sessions.length === 0 ? (
        <LoadingSpinner label="加载会话中…" />
      ) : (
        <div className="chat-page__grid">
          {showSidebar ? (
            <aside className="chat-page__sidebar">
              <AgentContextSidebar compact />
            </aside>
          ) : null}
          <main className="chat-page__main">
            <ChatPanel sessionId={currentSessionId} />
          </main>
        </div>
      )}
      <ConfirmDialog
        open={pendingDeleteId !== null}
        title="删除会话"
        message="此操作不可撤销。确定删除该会话吗?"
        confirmText="删除"
        cancelText="取消"
        destructive
        onConfirm={() => {
          if (pendingDeleteId) {
            void useAgentStore.getState().deleteSession(pendingDeleteId);
            setPendingDeleteId(null);
          }
        }}
        onCancel={() => setPendingDeleteId(null)}
      />
    </div>
  );
}

export default ChatPage;
