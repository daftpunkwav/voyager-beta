import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getApi } from '@/api/client';
import { useAgentStore } from '@/stores/agentStore';
import { useAuthStore } from '@/stores/authStore';
import { useUIStore } from '@/stores/uiStore';
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
  const addToast = useUIStore((s) => s.addToast);
  const [input, setInput] = useState('');
  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // 修复:三个点的"更多"按钮之前是死按钮;现在弹 popover,提供导出/复制/清空 3 个 action。
  // 点击 popover 外部或 Esc 键关闭(§a11y)。
  useEffect(() => {
    if (!moreOpen) return;
    const onDocDown = (e: globalThis.MouseEvent) => {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) {
        setMoreOpen(false);
      }
    };
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') setMoreOpen(false);
    };
    document.addEventListener('mousedown', onDocDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [moreOpen]);

  /** 把当前 messages 序列化为 markdown 文本。 */
  const exportMarkdown = (): string => {
    const lines: string[] = [];
    if (currentSession) {
      lines.push(`# ${currentSession.title || '对话'}`, '');
    }
    for (const m of messages) {
      const role = m.role === 'user' ? '我' : m.role === 'assistant' ? m.agent : 'system';
      lines.push(`## ${role}`, m.content || '', '');
    }
    return lines.join('\n');
  };

  /** 触发 markdown 文件下载(本地保存)。 */
  const handleExport = () => {
    if (messages.length === 0) {
      addToast({ type: 'warning', message: '当前会话无消息可导出' });
      return;
    }
    const md = exportMarkdown();
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    a.download = `voyager-chat-${currentSession?.id ?? 'untitled'}-${ts}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    addToast({ type: 'success', message: '对话已导出为 Markdown' });
    setMoreOpen(false);
  };

  /** 复制 markdown 到剪贴板。 */
  const handleCopy = async () => {
    if (messages.length === 0) {
      addToast({ type: 'warning', message: '当前会话无消息可复制' });
      return;
    }
    const md = exportMarkdown();
    try {
      await navigator.clipboard.writeText(md);
      addToast({ type: 'success', message: '对话已复制到剪贴板' });
    } catch {
      addToast({ type: 'error', message: '复制失败:浏览器不支持或权限不足' });
    }
    setMoreOpen(false);
  };

  /** 清空当前会话消息(本地状态)。 */
  const handleClear = () => {
    if (messages.length === 0) {
      addToast({ type: 'info', message: '当前会话已为空' });
      setMoreOpen(false);
      return;
    }
    if (!window.confirm(`确定清空当前会话(${messages.length} 条消息)?此操作不可撤销。`)) {
      return;
    }
    useAgentStore.setState({ messages: [], streamingContent: '', thinkingBuffer: '' });
    addToast({ type: 'success', message: '当前会话已清空' });
    setMoreOpen(false);
  };

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
          <button type="button" className="chat-icon-btn" title="导出对话" onClick={handleExport}>
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
          <div className="chat-more-wrap" ref={moreRef}>
            <button
              type="button"
              className="chat-icon-btn"
              title="更多"
              aria-label="更多操作"
              aria-haspopup="menu"
              aria-expanded={moreOpen}
              onClick={() => setMoreOpen((v) => !v)}
            >
              <svg viewBox="0 0 24 24" fill="currentColor" width={16} height={16}>
                <circle cx="5" cy="12" r="1.5" />
                <circle cx="12" cy="12" r="1.5" />
                <circle cx="19" cy="12" r="1.5" />
              </svg>
            </button>
            {moreOpen && (
              <div className="chat-more-pop" role="menu">
                <button type="button" role="menuitem" onClick={handleCopy}>
                  复制为 Markdown
                </button>
                <button type="button" role="menuitem" onClick={handleClear}>
                  清空当前会话
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {!llmOk && (
        <div className="degrade-tip" style={{ margin: '8px 20px 0' }}>
          LLM 未配置，请前往 <Link to="/settings">设置</Link> 配置 API Key。
        </div>
      )}

      <div className="chat-messages">
        {messages.length === 0 && !streaming && (
          <div className="chat-welcome" role="status">
            <div className="chat-welcome__orb" aria-hidden>
              <svg viewBox="0 0 64 64" width={56} height={56} fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="32" cy="32" r="22" />
                <path d="M22 26h20M22 32h14M22 38h18" />
              </svg>
            </div>
            <h3 className="chat-welcome__title">{agentDown ? 'Agent 服务暂时不可用' : '开始一次新的对话'}</h3>
            <p className="chat-welcome__desc">
              {agentDown
                ? '后端服务暂时不可达,稍后再试或前往 设置 检查 gateway 状态。'
                : '在下方的输入框中描述你想了解的开源项目、技术问题或想完成的任务;Agent 会自动调度合适的 subagent 协作完成。'}
            </p>
            {!agentDown && (
              <div className="chat-welcome__chips">
                <button type="button" className="chat-welcome__chip" onClick={() => { setInput('帮我找一个学习 WebGPU 的开源项目'); }}>
                  <span className="chat-welcome__chip-icon">🔍</span>推荐开源项目
                </button>
                <button type="button" className="chat-welcome__chip" onClick={() => { setInput('解释一下 React 19 的 useEffect 清理机制'); }}>
                  <span className="chat-welcome__chip-icon">💡</span>解释技术概念
                </button>
                <button type="button" className="chat-welcome__chip" onClick={() => { setInput('帮我分析 owner/repo 项目的架构'); }}>
                  <span className="chat-welcome__chip-icon">🧬</span>分析项目结构
                </button>
                <button type="button" className="chat-welcome__chip" onClick={() => { setInput('总结 owner/repo 最近 5 个 commit'); }}>
                  <span className="chat-welcome__chip-icon">📝</span>总结最近变更
                </button>
              </div>
            )}
          </div>
        )}
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
