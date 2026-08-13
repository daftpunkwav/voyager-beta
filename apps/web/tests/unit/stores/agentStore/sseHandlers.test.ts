/** 单测：SSE handler 模块（�?.1.10 N-01 拆分�?*/

import { describe, it, expect } from 'vitest';
import {
  handleTextDelta,
  handleThinking,
  handleError,
  handleSubagentThinking,
  handleSubagentText,
  handleDone,
  HANDLERS,
  type SseHandlerCtx,
} from '@/stores/agentStore/sseHandlers';

function makeCtx(initial: any = {}): SseHandlerCtx & { state: any } {
  const state = {
    streamingContent: '',
    thinkingBuffer: '',
    subagents: [],
    error: null,
    streaming: false,
    ...initial,
  };
  const ctx: SseHandlerCtx & { state: any } = {
    state,
    set: (partial: any) => {
      const p = typeof partial === 'function' ? partial(state) : partial;
      Object.assign(state, p);
    },
    get: () => state,
  };
  return ctx;
}

describe('text_delta handler', () => {
  it('appends content to streamingContent', () => {
    const ctx = makeCtx({ streamingContent: 'hello ' });
    handleTextDelta({ event: 'text_delta', data: { content: 'world' } }, ctx);
    expect(ctx.state.streamingContent).toBe('hello world');
  });

  it('ignores empty content', () => {
    const ctx = makeCtx({ streamingContent: 'x' });
    handleTextDelta({ event: 'text_delta', data: { content: '' } }, ctx);
    expect(ctx.state.streamingContent).toBe('x');
  });

  it('treats missing content as empty', () => {
    const ctx = makeCtx();
    handleTextDelta({ event: 'text_delta', data: {} }, ctx);
    expect(ctx.state.streamingContent).toBe('');
  });
});

describe('thinking handler', () => {
  it('appends content to thinkingBuffer', () => {
    const ctx = makeCtx({ thinkingBuffer: 'a' });
    handleThinking({ event: 'thinking', data: { content: 'b' } }, ctx);
    expect(ctx.state.thinkingBuffer).toBe('ab');
  });
});

describe('error handler', () => {
  it('sets error and clears streaming', () => {
    const ctx = makeCtx({ streaming: true });
    handleError({ event: 'error', data: { message: 'oops' } }, ctx);
    expect(ctx.state.error).toBe('oops');
    expect(ctx.state.streaming).toBe(false);
  });
});

describe('subagent_thinking handler', () => {
  it('appends to matching subagent thinking', () => {
    const ctx = makeCtx({
      subagents: [{ agentId: 'scout', thinking: 'a', output: '' }],
    });
    handleSubagentThinking(
      { event: 'subagent_thinking', data: { agent_id: 'scout', content: 'b' } },
      ctx
    );
    expect(ctx.state.subagents[0].thinking).toBe('ab');
  });

  it('skips when no matching agent_id', () => {
    const ctx = makeCtx({
      subagents: [{ agentId: 'scout', thinking: 'a', output: '' }],
    });
    handleSubagentThinking(
      { event: 'subagent_thinking', data: { content: 'b' } },
      ctx
    );
    expect(ctx.state.subagents[0].thinking).toBe('a');
  });
});

describe('subagent_text handler', () => {
  it('appends to matching subagent output', () => {
    const ctx = makeCtx({
      subagents: [{ agentId: 'mentor', thinking: '', output: 'a' }],
    });
    handleSubagentText(
      { event: 'subagent_text', data: { agent_id: 'mentor', content: 'b' } },
      ctx
    );
    expect(ctx.state.subagents[0].output).toBe('ab');
  });
});

describe('done handler', () => {
  it('is a no-op', () => {
    const ctx = makeCtx();
    expect(() => handleDone({ event: 'done', data: {} }, ctx)).not.toThrow();
  });
});

describe('HANDLERS registry', () => {
  it('covers the 6 expected events', () => {
    expect(Object.keys(HANDLERS).sort()).toEqual(
      ['done', 'error', 'subagent_text', 'subagent_thinking', 'text_delta', 'thinking'].sort()
    );
  });
});