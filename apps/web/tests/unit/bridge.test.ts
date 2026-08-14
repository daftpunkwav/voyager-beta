/** bridge client 契约:统一解 {result}/{error} 信封与网络错误映射。 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { callCapability, ServiceError } from '@/bridge/client';

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('callCapability', () => {
  it('成功时解出 result 字段', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch(200, { result: { id: 'n1', title: '链路测试' } }),
    );
    const out = await callCapability<{ id: string }>('notes', 'create_note', {
      title: '链路测试',
    });
    expect(out).toEqual({ id: 'n1', title: '链路测试' });
  });

  it('失败信封映射为 ServiceError(码/信息/提示)', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch(404, {
        error: {
          code: 'NOTES.NOT_FOUND',
          message: '笔记不存在',
          hint: '检查 id',
          trace_id: 't-1',
        },
      }),
    );
    const err = await callCapability('notes', 'get_note', { id: 'x' }).catch(
      (e) => e,
    );
    expect(err).toBeInstanceOf(ServiceError);
    expect(err.code).toBe('NOTES.NOT_FOUND');
    expect(err.message).toBe('笔记不存在');
    expect(err.hint).toBe('检查 id');
    expect(err.traceId).toBe('t-1');
  });

  it('网络不可达映射为 NETWORK 错误', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('fail')));
    const err = await callCapability('notes', 'list_notes').catch((e) => e);
    expect(err).toBeInstanceOf(ServiceError);
    expect(err.code).toBe('NETWORK');
  });

  it('请求带 X-Trace-Id 与 JSON 体', async () => {
    const fetchMock = mockFetch(200, { result: {} });
    vi.stubGlobal('fetch', fetchMock);
    await callCapability('llm', 'complete', { messages: [] });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/llm/capabilities/complete');
    expect(init.method).toBe('POST');
    expect((init.headers as Record<string, string>)['X-Trace-Id']).toMatch(
      /^[0-9a-f-]{36}$/,
    );
    expect(init.body).toBe('{"messages":[]}');
  });
});
