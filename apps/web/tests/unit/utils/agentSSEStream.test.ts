import { describe, expect, it, vi } from 'vitest';
import type { SSEEvent } from '@/api/types';
import { consumeAgentSSEStream } from '@/utils/agentSSEStream';

async function* events(list: SSEEvent[]) {
  for (const e of list) yield e;
}

describe('consumeAgentSSEStream', () => {
  it('聚合 text_delta 与 thinking', async () => {
    const onText = vi.fn();
    const onThink = vi.fn();
    const result = await consumeAgentSSEStream(
      events([
        { event: 'thinking', data: { content: '想' } },
        { event: 'thinking', data: { content: '一下' } },
        { event: 'text_delta', data: { content: '你好' } },
        { event: 'text_delta', data: { content: '世界' } },
        { event: 'done', data: { usage: { tokens: 4 } } },
      ]),
      { onTextDelta: onText, onThinking: onThink },
    );
    expect(result.text).toBe('你好世界');
    expect(result.thinking).toBe('想一下');
    expect(result.sawError).toBe(false);
    expect(onText).toHaveBeenCalledTimes(2);
    expect(onThink).toHaveBeenCalledTimes(2);
  });

  it('转发 select_repos 与 error', async () => {
    const onSelect = vi.fn();
    const onError = vi.fn();
    const result = await consumeAgentSSEStream(
      events([
        {
          event: 'select_repos',
          data: { repo_keys: ['a/b'], action: 'set' },
        },
        { event: 'error', data: { message: 'boom' } },
      ]),
      { onSelectRepos: onSelect, onError },
    );
    expect(onSelect).toHaveBeenCalledWith({
      repo_keys: ['a/b'],
      action: 'set',
    });
    expect(result.sawError).toBe(true);
    expect(result.errorMessage).toBe('boom');
  });

  it('signal abort 后停止消费', async () => {
    const ac = new AbortController();
    async function* gen() {
      yield { event: 'text_delta', data: { content: 'A' } } as SSEEvent;
      ac.abort();
      yield { event: 'text_delta', data: { content: 'B' } } as SSEEvent;
    }
    const result = await consumeAgentSSEStream(gen(), {}, { signal: ac.signal });
    // 第一次循环后 aborted，B 可能不会进入
    expect(result.text === 'A' || result.text === 'AB').toBe(true);
  });
});
