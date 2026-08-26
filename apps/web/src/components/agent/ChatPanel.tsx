import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getApi } from '@/api/client';
import { useAgentStore } from '@/stores/agentStore';
import { useAuthStore } from '@/stores/authStore';
import { useSettings } from '@/hooks/useSettings';
import { ensureAgentQuestion } from '@/utils/agentQuestion';
import { AgentSelector } from './AgentSelector';
import { MessageBubble } from './MessageBubble';
import { StreamRenderer } from './StreamRenderer';
import { LiveQuestionModal } from './QuestionHistoryCard';
import { RunTracePanel } from './RunTracePanel';
import { AGENT_INITIALS, AGENT_ROLE_LABELS } from '@/utils/labels';
import { snapshotSubagents, snapshotToolCalls } from '@/utils/runTrace';

export interface ChatPanelProps {
  /** 左侧对话历史是否已收起 */
  sessionListCollapsed?: boolean;
  /** 右侧上下文是否已收起 */
  contextPanelCollapsed?: boolean;
  onToggleSessionList?: () => void;
  onToggleContextPanel?: () => void;
}

function PanelLeftIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" width={16} height={16}>
      <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
      <path d="M9 4.5v15" />
    </svg>
  );
}

function PanelRightIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" width={16} height={16}>
      <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
      <path d="M15 4.5v15" />
    </svg>
  );
}

export function ChatPanel({
  sessionListCollapsed = false,
  contextPanelCollapsed = false,
  onToggleSessionList,
  onToggleContextPanel,
}: ChatPanelProps) {
  const sessions = useAgentStore((s) => s.sessions);
  const currentSessionId = useAgentStore((s) => s.currentSessionId);
  const messages = useAgentStore((s) => s.messages);
  const streaming = useAgentStore((s) => s.streaming);
  const streamingContent = useAgentStore((s) => s.streamingContent);
  const thinkingBuffer = useAgentStore((s) => s.thinkingBuffer);
  const pendingQuestionRaw = useAgentStore((s) => s.pendingQuestion);
  const toolCalls = useAgentStore((s) => s.toolCalls);
  const subagents = useAgentStore((s) => s.subagents);
  const activeAgent = useAgentStore((s) => s.activeAgent);
  const error = useAgentStore((s) => s.error);
  const sendMessage = useAgentStore((s) => s.sendMessage);
  const answerQuestion = useAgentStore((s) => s.answerQuestion);
  const skipQuestion = useAgentStore((s) => s.skipQuestion);
  const { settings } = useSettings();
  const user = useAuthStore((s) => s.user);
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  const pendingQuestion = useMemo(
    () => (pendingQuestionRaw ? ensureAgentQuestion(pendingQuestionRaw) : null),
    [pendingQuestionRaw]
  );

  const profilesQ = useQuery({
    queryKey: ['agentProfiles'],
    queryFn: async () => (await getApi().getAgentProfiles()).data,
  });
  const profiles = profilesQ.data ?? [];
  /** Agent 模块不可用（profiles 是 agent 域首个调用，503 即服务不可用） */
  const agentDown = profilesQ.isError;

  const { data: sessionDetail } = useQuery({
    queryKey: ['agentSession', currentSessionId],
    enabled: Boolean(currentSessionId),
    queryFn: async () => {
      if (!currentSessionId) return null;
      return (await getApi().getAgentSession(currentSessionId)).data;
    },
  });

  const boundCount = useMemo(() => {
    if (!sessionDetail) return 0;
    if (sessionDetail.project_ids?.length) return sessionDetail.project_ids.length;
    return sessionDetail.project_id ? 1 : 0;
  }, [sessionDetail]);

  const profile = profiles.find((p) => p.id === activeAgent);
  const currentSession = sessions.find((s) => s.id === currentSessionId);
  const llmOk = settings?.llm_configured !== false;
  const modelName = settings?.llm_model ?? 'gpt-4o';

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent, pendingQuestion]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || streaming || pendingQuestion || agentDown) return;
    setInput('');
    await sendMessage(text);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  return (
    <>
      <header className="chat-header">
        {onToggleSessionList && (
          <button
            type="button"
            className={`chat-icon-btn chat-panel-toggle ${sessionListCollapsed ? '' : 'is-on'}`}
            onClick={onToggleSessionList}
            aria-label={sessionListCollapsed ? '展开对话历史' : '收起对话历史'}
            aria-pressed={!sessionListCollapsed}
            data-testid="session-list-toggle"
            title={sessionListCollapsed ? '展开对话历史' : '收起对话历史'}
          >
            <PanelLeftIcon />
          </button>
        )}
        <AgentSelector profiles={profiles} />
        <div className="chat-title">
          <h2>{currentSession?.title ?? '新对话'}</h2>
          <div className="ctx">
            {boundCount > 0 ? `${boundCount} 个项目上下文` : '未绑定项目'} ·{' '}
            {user?.username ?? 'guest'} · {modelName}
            <span className="dot" />
            <span style={{ color: 'var(--brand-500)' }}>Hub 智能调度 · 7 Agent 在线</span>
          </div>
        </div>
        <div className="chat-actions">
          {onToggleContextPanel && (
            <button
              type="button"
              className={`chat-icon-btn chat-panel-toggle ${contextPanelCollapsed ? '' : 'is-on'}`}
              onClick={onToggleContextPanel}
              aria-label={contextPanelCollapsed ? '展开上下文面板' : '收起上下文面板'}
              aria-pressed={!contextPanelCollapsed}
              data-testid="context-panel-toggle"
              title={contextPanelCollapsed ? '展开上下文面板' : '收起上下文面板'}
            >
              <PanelRightIcon />
            </button>
          )}
          <button type="button" className="chat-icon-btn" title="导出对话">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              width={16}
              height={16}
            >
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
              <path d="M7 10l5 5 5-5M12 15V3" />
            </svg>
          </button>
          <button type="button" className="chat-icon-btn" title="更多">
            <svg viewBox="0 0 24 24" fill="currentColor" width={16} height={16}>
              <circle cx="5" cy="12" r="1.5" />
              <circle cx="12" cy="12" r="1.5" />
              <circle cx="19" cy="12" r="1.5" />
            </svg>
          </button>
        </div>
      </header>

      {!llmOk && (
        <div className="degrade-tip" style={{ margin: '8px 20px 0' }}>
          LLM 未配置，请前往 <Link to="/settings">设置</Link> 配置 API Key。
        </div>
      )}

      <div className="chat-messages">
        {messages.map((m) => (
          <MessageBubble
            key={m.id}
            message={m}
            agentName={profiles.find((p) => p.id === m.agent)?.name}
          />
        ))}
        {streaming && !pendingQuestion && (
          <div className="msg">
            <div className={`msg-avatar agent-${activeAgent}`}>
              {AGENT_INITIALS[activeAgent] ?? 'A'}
            </div>
            <div className="msg-body">
              <div className="msg-head">
                <span className="msg-name">{profile?.name ?? activeAgent}</span>
                <span className="msg-role">{AGENT_ROLE_LABELS[activeAgent]}</span>
                <span className="streaming-indicator">
                  <span className="streaming-dot" />
                  {activeAgent === 'hub' &&
                  (/汇总|合并|评估/.test(thinkingBuffer || '') ||
                    subagents.some((s) => s.status === 'running'))
                    ? /汇总|合并/.test(thinkingBuffer || '')
                      ? '汇总中'
                      : /评估/.test(thinkingBuffer || '')
                        ? '评估中'
                        : subagents.some((s) => s.status === 'running')
                          ? '调度中'
                          : '生成中'
                    : '生成中'}
                </span>
              </div>
              <div className="msg-content">
                <StreamRenderer
                  content={streamingContent}
                  thinking={thinkingBuffer}
                  streaming={streaming}
                />
                <RunTracePanel
                  toolCalls={snapshotToolCalls(toolCalls)}
                  subagents={snapshotSubagents(subagents, thinkingBuffer, {
                    finalizeRunning: false,
                  })}
                />
              </div>
            </div>
          </div>
        )}
        {error && <div className="error-banner">{error}</div>}
        {agentDown && (
          <div className="error-banner" data-testid="agent-down-banner">
            Agent 服务不可用：{(profilesQ.error as Error)?.message || '请检查后端服务'}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {pendingQuestion && (
        <LiveQuestionModal
          question={pendingQuestion}
          agentLabel={profile?.name ?? activeAgent}
          onSubmit={(a) => void answerQuestion(a)}
          onSkip={skipQuestion}
        />
      )}

      <div className="chat-input-wrap">
        <div className="chat-input">
          <textarea
            className="chat-textarea"
            data-testid="chat-input"
            rows={2}
            placeholder="问 Voyager 任何关于开源项目的问题..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={streaming || Boolean(pendingQuestion) || !llmOk || agentDown}
          />
          <div className="chat-toolbar">
            <span className={`ctx-chip ${boundCount > 0 ? 'active' : ''}`}>
              {boundCount > 0 ? `${boundCount} 个项目上下文` : '无项目上下文'}
            </span>
            <div className="spacer" />
            <span
              style={{ fontSize: 11, color: 'var(--text-400)', fontFamily: 'var(--font-mono)' }}
            >
              {input.length} 字符
            </span>
            <button
              type="button"
              className="send-btn"
              title="发送 (Enter)"
              onClick={() => void handleSend()}
              disabled={streaming || Boolean(pendingQuestion) || !llmOk || agentDown}
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                width={14}
                height={14}
              >
                <path d="M5 12l14 0M13 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        </div>
        <div className="chat-hint">
          <span>
            <kbd>Enter</kbd> 发送 · <kbd>Shift</kbd>+<kbd>Enter</kbd> 换行
          </span>
          <span>SSE 流式输出已启用</span>
        </div>
      </div>
    </>
  );
}
