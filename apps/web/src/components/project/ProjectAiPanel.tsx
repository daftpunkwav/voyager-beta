import { useEffect, useRef } from 'react';
import type { AgentDefinition } from '@/constants/agentCatalog';
import type { AgentId } from '@/api/types';
import { StreamRenderer } from '@/components/agent/StreamRenderer';
import { AGENT_INITIALS } from '@/utils/labels';
import { GLASS_OUTER } from '@/constants/glassTokens';

export interface ProjectAiLine {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  thinking?: string;
  agentId?: AgentId;
}

interface ProjectAiPanelProps {
  projectName: string;
  agents: AgentDefinition[];
  activeAgent: AgentId;
  lines: ProjectAiLine[];
  streaming: boolean;
  streamContent: string;
  streamThinking: string;
  onSelectAgent: (id: AgentId) => void;
  onRun: () => void;
  onAbort: () => void;
}

export function ProjectAiPanel({
  projectName,
  agents,
  activeAgent,
  lines,
  streaming,
  streamContent,
  streamThinking,
  onSelectAgent,
  onRun,
  onAbort,
}: ProjectAiPanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const activeMeta = agents.find((a) => a.id === activeAgent) ?? agents[0];
  const initial = AGENT_INITIALS[activeAgent] ?? activeMeta?.name?.[0] ?? 'A';

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [lines, streaming, streamContent, streamThinking]);

  return (
    <div
      className={`pd-ai-panel embed-agent-chat ${GLASS_OUTER}`}
      data-testid="project-ai-panel"
    >
      <header className="embed-agent-chat__head pd-ai-chat-head">
        <div className={`agent-avatar agent-${activeAgent} active`} aria-hidden>
          <span>{initial}</span>
        </div>
        <div className="pd-ai-chat-identity">
          <div className="embed-agent-chat__title">
            {activeMeta?.name ?? 'Agent'} · {activeMeta?.tagline ?? '分析'}
          </div>
          <div className="embed-agent-chat__sub">针对 {projectName} 的一次性项目分析</div>
        </div>
        <div className="pd-ai-agent-switch" role="tablist" aria-label="选择分析 Agent">
          {agents.map((a) => (
            <button
              key={a.id}
              type="button"
              role="tab"
              className={`pd-ai-chip ${activeAgent === a.id ? 'is-active' : ''}`}
              aria-selected={activeAgent === a.id}
              disabled={streaming}
              title={a.intro}
              onClick={() => onSelectAgent(a.id as AgentId)}
            >
              {a.name}
            </button>
          ))}
        </div>
      </header>

      <div className="embed-agent-chat__messages pd-ai-chat-messages">
        {lines.map((l) => (
          <div key={l.id} className={`embed-msg embed-msg--${l.role}`}>
            {l.role === 'user' ? (
              l.content
            ) : (
              <StreamRenderer content={l.content} thinking={l.thinking} streaming={false} />
            )}
          </div>
        ))}
        {streaming && (
          <div className="embed-msg embed-msg--assistant embed-msg--streaming">
            {streamContent || streamThinking ? (
              <StreamRenderer
                content={streamContent}
                thinking={streamThinking || undefined}
                streaming
              />
            ) : (
              <span className="embed-msg--typing">
                {activeMeta?.name ?? 'Agent'} 分析中…
              </span>
            )}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="embed-agent-chat__input pd-ai-chat-actions">
        <p className="pd-ai-chat-hint">
          {streaming
            ? '分析进行中，可中止后换专家重试。'
            : '选择专家后开始分析；结果以消息流展示。追问请到 Agent 对话。'}
        </p>
        {streaming ? (
          <button
            type="button"
            className="btn btn-sm"
            onClick={onAbort}
            data-testid="project-ai-abort"
          >
            中止
          </button>
        ) : (
          <button
            type="button"
            className="btn btn-primary btn-sm pd-ai-run-btn"
            onClick={onRun}
            data-testid="project-ai-run"
          >
            {lines.some((l) => l.role === 'assistant') ? '重新分析' : '开始分析'}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" width={14} height={14} aria-hidden>
              <path d="M5 12h14M13 5l7 7-7 7" />
            </svg>
          </button>
        )}
      </div>

      <footer className="embed-agent-chat__footer">
        <span className="mono">{activeMeta?.name ?? 'Agent'}</span>
        <span className="embed-agent-chat__hint">消息流 · 一次性分析</span>
      </footer>
    </div>
  );
}
