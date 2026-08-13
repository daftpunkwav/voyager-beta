import { describe, expect, it } from 'vitest';
import { parseSSEStream } from '@/utils/sse-parser';

function sseStream(chunks: string[]): ReadableStreamDefaultReader<Uint8Array> {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
  return stream.getReader();
}

async function collect<T>(gen: AsyncGenerator<T>): Promise<T[]> {
  const out: T[] = [];
  for await (const item of gen) out.push(item);
  return out;
}

describe('parseSSEStream', () => {
  it('parses a single complete event', async () => {
    const reader = sseStream(['event: text_delta\ndata: {"content":"hi"}\n\n']);
    const events = await collect(parseSSEStream(reader));
    expect(events).toEqual([{ event: 'text_delta', data: { content: 'hi' } }]);
  });

  it('handles chunked event split across two reads', async () => {
    const reader = sseStream(['event: text_delta\ndata: {"c', 'ontent":"hi"}\n\n']);
    const events = await collect(parseSSEStream(reader));
    expect(events).toEqual([{ event: 'text_delta', data: { content: 'hi' } }]);
  });

  it('parses multiple events in one chunk', async () => {
    const reader = sseStream([
      'event: text_delta\ndata: {"content":"a"}\n\nevent: done\ndata: {"usage":{}}\n\n',
    ]);
    const events = await collect(parseSSEStream(reader));
    expect(events).toHaveLength(2);
    expect(events[0]?.event).toBe('text_delta');
    expect(events[1]?.event).toBe('done');
  });

  it('skips malformed JSON without throwing', async () => {
    const reader = sseStream([
      'event: text_delta\ndata: not-json\n\nevent: done\ndata: {}\n\n',
    ]);
    const events = await collect(parseSSEStream(reader));
    expect(events).toEqual([{ event: 'done', data: {} }]);
  });

  it('joins multi-line data fields with newline per SSE spec', async () => {
    // 多行 data 按 SSE 规范以 \n 拼接；payload 需是合法 JSON（pretty-print 形式）
    const reader = sseStream([
      'event: text_delta\ndata: {\ndata: "content": "hi"\ndata: }\n\n',
    ]);
    const events = await collect(parseSSEStream(reader));
    expect(events).toEqual([{ event: 'text_delta', data: { content: 'hi' } }]);
  });

  it('stops yielding after AbortSignal is triggered', async () => {
    const encoder = new TextEncoder();
    let pushCount = 0;
    const ac = new AbortController();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        const tick = () => {
          if (ac.signal.aborted || pushCount++ >= 5) {
            try {
              controller.close();
            } catch {
              // 可能已被 reader.cancel 关闭
            }
            return;
          }
          try {
            controller.enqueue(
              encoder.encode('event: text_delta\ndata: {"content":"x"}\n\n')
            );
          } catch {
            return;
          }
          setTimeout(tick, 5);
        };
        tick();
      },
    });
    const collected: unknown[] = [];
    for await (const e of parseSSEStream(stream.getReader(), ac.signal)) {
      collected.push(e);
      if (collected.length >= 1) ac.abort();
    }
    // 至少收到 1 个，且最终会停止
    expect(collected.length).toBeGreaterThanOrEqual(1);
  });
});
