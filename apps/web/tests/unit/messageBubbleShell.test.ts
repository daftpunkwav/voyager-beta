import { describe, expect, it } from 'vitest';
import type { AgentMessage } from '@/api/types';

/**
 * 与 MessageBubble.isEmptyAssistantShell 对齐的判定（单测用）。
 * 有 tool_calls / subagents 时不得当作空壳吞掉。
 */
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
  return !think;
}

describe('assistant shell visibility', () => {
  it('纯动作踪迹消息不应被当作空壳', () => {
    const msg: AgentMessage = {
      id: '1',
      session_id: 's',
      agent: 'scribe',
      role: 'assistant',
      content: '',
      tool_calls: [
        {
          name: 'create_note',
          args: {},
          result: { __action__: 'note_created', summary: '已创建', ok: true },
        },
      ],
      created_at: new Date().toISOString(),
    };
    expect(isEmptyAssistantShell(msg)).toBe(false);
  });

  it('无正文无思考无踪迹才是空壳', () => {
    const msg: AgentMessage = {
      id: '2',
      session_id: 's',
      agent: 'hub',
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString(),
    };
    expect(isEmptyAssistantShell(msg)).toBe(true);
  });
});
