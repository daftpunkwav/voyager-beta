import type { AgentId, ToolCallData } from '@/api/types';
import { personaDisplayName } from '@/constants/personas';

export interface SubagentTrace {
  agentId: AgentId;
  task?: string;
  reason?: string;
  status: 'running' | 'ok' | 'question' | 'error';
  /** 专家思考过程（嵌套 SSE 或从 Hub 合流思考拆出） */
  thinking?: string;
  /** 专家正文输出（嵌套 SSE） */
  output?: string;
}

export function agentDisplayName(agentId: string): string {
  return personaDisplayName(agentId);
}

/** 从合流 thinking 中拆出 【Scout】… 片段 */
export function extractExpertThinking(
  fullThinking: string | undefined | null,
  agentId: string
): string {
  const text = (fullThinking ?? '').trim();
  if (!text) return '';
  const name = agentDisplayName(agentId);
  const re = new RegExp(
    `【${name}】\\s*\\n?([\\s\\S]*?)(?=\\n【[A-Za-z\\u4e00-\\u9fff]+】|$)`
  );
  const m = text.match(re);
  return (m?.[1] ?? '').trim();
}

export function snapshotToolCalls(
  toolCalls: Map<string, { name: string; args: Record<string, unknown>; result?: unknown }>
): ToolCallData[] {
  return Array.from(toolCalls.entries())
    .filter(([, tc]) => tc.name !== 'ask_user')
    .map(([, tc]) => ({
      name: tc.name,
      args: tc.args ?? {},
      ...(tc.result !== undefined ? { result: tc.result } : {}),
    }));
}

export function snapshotSubagents(
  subagents: Array<{
    agentId: AgentId;
    task?: string;
    reason?: string;
    status: SubagentTrace['status'];
    thinking?: string;
    output?: string;
  }>,
  fullThinking: string | undefined | null,
  opts?: { finalizeRunning?: boolean }
): SubagentTrace[] {
  const finalizeRunning = opts?.finalizeRunning !== false;
  return subagents.map((sa) => {
    const nestedThink = (sa.thinking ?? '').trim();
    const fallbackThink = nestedThink
      ? nestedThink
      : extractExpertThinking(fullThinking, sa.agentId);
    const output = (sa.output ?? '').trim();
    return {
      agentId: sa.agentId,
      task: sa.task,
      reason: sa.reason,
      status:
        finalizeRunning && sa.status === 'running' ? 'ok' : sa.status,
      ...(fallbackThink ? { thinking: fallbackThink } : {}),
      ...(output ? { output } : {}),
    };
  });
}
