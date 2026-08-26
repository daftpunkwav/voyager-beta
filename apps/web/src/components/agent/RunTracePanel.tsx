import { useState } from 'react';
import type { AgentId, ToolCallData } from '@/api/types';
import { ToolCallCard } from '@/components/agent/ToolCallCard';
import { ActionResultCard } from '@/components/agent/ActionResultCard';
import { AGENT_INITIALS, AGENT_ROLE_LABELS } from '@/utils/labels';
import { displaySwitchReason } from '@/utils/agentSwitchDisplay';
import { actionSummaryFromToolResult, parseActionResult } from '@/utils/actionResult';
import {
  agentDisplayName,
  type SubagentTrace,
} from '@/utils/runTrace';

interface RunTracePanelProps {
  toolCalls?: ToolCallData[];
  subagents?: SubagentTrace[];
  /** 流式中可选：点击专家时高亮/外控展开 */
  defaultOpenAgentId?: string | null;
}

function subagentStatusLabel(
  sa: SubagentTrace,
  actionHint: string | null
): string {
  if (sa.status === 'running') return '执行中';
  if (sa.status === 'question') return '等待回答';
  if (sa.status === 'error') return '失败';
  if (actionHint) return actionHint;
  return '完成';
}

/** 落盘后的调度/工具踪迹：结果卡优先，技术细节可展开 */
export function RunTracePanel({
  toolCalls,
  subagents,
  defaultOpenAgentId = null,
}: RunTracePanelProps) {
  const [openId, setOpenId] = useState<string | null>(defaultOpenAgentId);
  const tools = (toolCalls ?? []).filter((t) => t.name !== 'ask_user');
  const agents = subagents ?? [];
  const actionTools = tools.filter((t) => parseActionResult(t.result) != null);
  const otherTools = tools.filter((t) => parseActionResult(t.result) == null);
  const latestActionSummary =
    [...actionTools]
      .reverse()
      .map((t) => actionSummaryFromToolResult(t.result))
      .find(Boolean) ?? null;

  if (tools.length === 0 && agents.length === 0) return null;

  return (
    <div className="run-trace" data-testid="run-trace">
      {actionTools.length > 0 && (
        <div className="run-trace__actions" aria-label="执行结果">
          {actionTools.map((tc, i) => (
            <ActionResultCard
              key={`act_${tc.name}_${i}`}
              result={tc.result}
              toolName={tc.name}
            />
          ))}
        </div>
      )}
      {agents.length > 0 && (
        <div className="hub-subagents" aria-label="内嵌 Agent">
          {agents.map((sa) => {
            const open = openId === sa.agentId;
            const hasThinking = Boolean(sa.thinking?.trim());
            const hasOutput = Boolean(sa.output?.trim());
            const hasDetail = hasThinking || hasOutput;
            return (
              <div key={sa.agentId} className="hub-subagent-wrap">
                <button
                  type="button"
                  className="hub-subagent hub-subagent--btn"
                  data-status={sa.status}
                  data-open={open ? '1' : '0'}
                  aria-expanded={hasDetail ? open : undefined}
                  disabled={!hasDetail}
                  onClick={() => {
                    if (!hasDetail) return;
                    setOpenId((cur) => (cur === sa.agentId ? null : sa.agentId));
                  }}
                >
                  <span className={`hub-subagent__avatar agent-${sa.agentId}`}>
                    {AGENT_INITIALS[sa.agentId as AgentId] ??
                      sa.agentId[0]?.toUpperCase()}
                  </span>
                  <div className="hub-subagent__meta">
                    <span className="hub-subagent__name">
                      {agentDisplayName(sa.agentId)}
                      <span className="hub-subagent__role">
                        {AGENT_ROLE_LABELS[sa.agentId as AgentId] ?? ''}
                      </span>
                    </span>
                    <span className="hub-subagent__status">
                      {subagentStatusLabel(
                        sa,
                        agents.length === 1 ? latestActionSummary : null
                      )}
                      {hasDetail ? (open ? ' · 收起过程' : ' · 查看过程') : ''}
                    </span>
                    {sa.reason && (
                      <span className="hub-subagent__reason" title={sa.reason}>
                        {displaySwitchReason(sa.reason, sa.agentId, 64)}
                      </span>
                    )}
                  </div>
                </button>
                {open && hasDetail && (
                  <div className="hub-subagent__detail" data-testid="subagent-detail">
                    {hasThinking && (
                      <div className="hub-subagent__section">
                        <div className="hub-subagent__section-label">思考过程</div>
                        <pre
                          className="hub-subagent__thinking"
                          data-testid="subagent-thinking"
                        >
                          {sa.thinking}
                        </pre>
                      </div>
                    )}
                    {hasOutput && (
                      <div className="hub-subagent__section">
                        <div className="hub-subagent__section-label">专家输出</div>
                        <pre
                          className="hub-subagent__output"
                          data-testid="subagent-output"
                        >
                          {sa.output}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      {(otherTools.length > 0 || actionTools.length > 0) && (
        <details className="run-trace__tech" open={actionTools.length === 0}>
          <summary className="run-trace__tech-summary">
            技术详情（{tools.length} 次工具调用）
          </summary>
          <div className="run-trace__tech-body">
            {tools.map((tc, i) => (
              <ToolCallCard
                key={`${tc.name}_${i}`}
                name={tc.name}
                args={tc.args}
                result={tc.result}
                showAction={false}
              />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
