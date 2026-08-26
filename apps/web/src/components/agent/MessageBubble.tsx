import type { AgentMessage } from '@/api/types';
import { useState } from 'react';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
import {
  isStatusOnlyThinking,
  StreamRenderer,
} from '@/components/agent/StreamRenderer';
import { formatMessageTime } from '@/utils/date';
import { AGENT_INITIALS, AGENT_ROLE_LABELS } from '@/utils/labels';
import {
  ensureAgentQuestion,
  recoverQuestionFromText,
  tryParseAnswerDump,
} from '@/utils/agentQuestion';
import { displaySwitchReason } from '@/utils/agentSwitchDisplay';
import { QuestionAnswerCard, QuestionOfferCard } from './QuestionHistoryCard';
import { RunTracePanel } from './RunTracePanel';

const LONG_MSG_CHARS = 2800;

interface MessageBubbleProps {
  message: AgentMessage;
  agentName?: string;
}

/** 无正文且无可展示思考/踪迹时视为空消息（含仅状态行） */
function isEmptyAssistantShell(message: AgentMessage): boolean {
  if (message.role !== 'assistant') return false;
  if (message.agent_switch || message.question || message.question_answer) {
    return false;
  }
  if ((message.tool_calls?.length ?? 0) > 0) return false;
  if ((message.subagents?.length ?? 0) > 0) return false;
  const body = (message.content ?? '').trim();
  if (body) return false;
  const think = (message.thinking ?? '').trim();
  if (!think) return true;
  return isStatusOnlyThinking(think);
}

export function MessageBubble({ message, agentName }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const agentId = message.agent;
  const name = agentName ?? agentId.charAt(0).toUpperCase() + agentId.slice(1);
  const role = AGENT_ROLE_LABELS[agentId] ?? agentId;
  const initial = isUser ? 'Z' : (AGENT_INITIALS[agentId] ?? name[0]);
  const [expanded, setExpanded] = useState(false);

  if (isEmptyAssistantShell(message)) {
    return null;
  }

  if (message.agent_switch) {
    const pretty = (id: string) =>
      ({
        hub: 'Hub',
        scout: 'Scout',
        mentor: 'Mentor',
        navigator: 'Navigator',
        curator: 'Curator',
        scribe: 'Scribe',
        atlas: 'Atlas',
      }[id] ?? id);
    const fromId = message.agent_switch.from;
    const toId = message.agent_switch.to;
    const from = pretty(fromId);
    const to = pretty(toId);
    const role = AGENT_ROLE_LABELS[toId] ?? '';
    const rawReason = message.agent_switch.reason?.trim();
    const reason = displaySwitchReason(rawReason, toId, 96);
    const showReason = Boolean(reason) && reason !== role;
    return (
      <div className="msg msg--switch" data-testid="agent-switch-notice">
        <div className="agent-switch" role="status" aria-label={`切换 ${from} 到 ${to}`}>
          <span className="agent-switch__line" aria-hidden />
          <div className="agent-switch__core">
            <span className="agent-switch__from">{from}</span>
            <span className="agent-switch__arrow" aria-hidden>
              →
            </span>
            <span className="agent-switch__to">{to}</span>
            {role ? <span className="agent-switch__role">{role}</span> : null}
          </div>
          <span className="agent-switch__line" aria-hidden />
        </div>
        {showReason && <p className="agent-switch__reason">{reason}</p>}
      </div>
    );
  }

  if (message.question) {
    const q = ensureAgentQuestion(message.question) ?? message.question;
    return (
      <div className="msg">
        <div className={`msg-avatar agent-${agentId}`}>{initial}</div>
        <div className="msg-body">
          <div className="msg-head">
            <span className="msg-name">{name}</span>
            <span className="msg-role">{role}</span>
            <span className="msg-time">{formatMessageTime(message.created_at)}</span>
          </div>
          <QuestionOfferCard question={q} agentName={name} />
        </div>
      </div>
    );
  }

  if (message.question_answer) {
    return (
      <div className="msg msg-user">
        <div className="msg-avatar">{initial}</div>
        <div className="msg-body">
          <div className="msg-head">
            <span className="msg-name">你</span>
            <span className="msg-time">{formatMessageTime(message.created_at)}</span>
          </div>
          <QuestionAnswerCard record={message.question_answer} />
        </div>
      </div>
    );
  }

  const recovered =
    !isUser && message.content ? recoverQuestionFromText(message.content) : null;
  if (recovered) {
    return (
      <div className="msg">
        <div className={`msg-avatar agent-${agentId}`}>{initial}</div>
        <div className="msg-body">
          <div className="msg-head">
            <span className="msg-name">{name}</span>
            <span className="msg-role">{role}</span>
            <span className="msg-time">{formatMessageTime(message.created_at)}</span>
          </div>
          <QuestionOfferCard question={recovered} agentName={name} />
        </div>
      </div>
    );
  }

  const answerDump = isUser && message.content ? tryParseAnswerDump(message.content) : null;
  if (answerDump) {
    return (
      <div className="msg msg-user">
        <div className="msg-avatar">{initial}</div>
        <div className="msg-body">
          <div className="msg-head">
            <span className="msg-name">你</span>
            <span className="msg-time">{formatMessageTime(message.created_at)}</span>
          </div>
          <QuestionAnswerCard record={answerDump} />
        </div>
      </div>
    );
  }

  const isLegacyAnswer = isUser && (message.content ?? '').startsWith('[反问回答]');
  const isLegacySkip = isUser && (message.content ?? '').startsWith('[跳过反问]');
  const contentLen = (message.content ?? '').length;
  const isLong = !isUser && contentLen > LONG_MSG_CHARS;

  return (
    <div className={`msg ${isUser ? 'msg-user' : ''}`}>
      <div className={`msg-avatar ${isUser ? '' : `agent-${agentId}`}`}>{initial}</div>
      <div className="msg-body">
        <div className="msg-head">
          <span className="msg-name">{isUser ? '你' : name}</span>
          {!isUser && <span className="msg-role">{role}</span>}
          <span className="msg-time">{formatMessageTime(message.created_at)}</span>
        </div>
        <div
          className={`msg-content ${isLegacyAnswer || isLegacySkip ? 'msg-content--qa-legacy' : ''}`}
        >
          {!isUser && (message.thinking || message.content) ? (
            <StreamRenderer
              content={message.content ?? ''}
              thinking={message.thinking}
              streaming={false}
              collapseBody={isLong && !expanded}
            />
          ) : (
            message.content && <MarkdownRenderer content={message.content} />
          )}
          {!isUser && (
            <RunTracePanel
              toolCalls={message.tool_calls}
              subagents={message.subagents}
            />
          )}
        </div>
        {isLong && (
          <button
            type="button"
            className="msg-expand-btn"
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? '收起长文' : '展开全文'}
          </button>
        )}
      </div>
    </div>
  );
}
