import { describe, expect, it } from 'vitest';
import { isStreamSessionActive } from '@/utils/streamSessionGuard';
import { isStatusLine, persistableThinking } from '@/components/agent/StreamRenderer';

describe('isStreamSessionActive', () => {
  it('same session stays active', () => {
    expect(isStreamSessionActive('sess-a', 'sess-a')).toBe(true);
  });

  it('switched session is inactive', () => {
    expect(isStreamSessionActive('sess-a', 'sess-b')).toBe(false);
  });

  it('null origin or current is inactive', () => {
    expect(isStreamSessionActive(null, 'sess-a')).toBe(false);
    expect(isStreamSessionActive('sess-a', null)).toBe(false);
    expect(isStreamSessionActive(undefined, undefined)).toBe(false);
  });
});

describe('dispatch status scaffolding', () => {
  it('treats dispatch status as status line not real thinking', () => {
    const line = '[状态] 调度 · Navigator · 用户明确要路径与里程碑';
    expect(isStatusLine(line)).toBe(true);
    expect(persistableThinking(`${line}\n`)).toBe('');
  });
});
