/**
 * §4.2.18: actionResult 测试加强 — 验证返回的具体字段而非仅 toBeDefined
 */
import { describe, expect, it } from 'vitest';
import { parseActionResult } from '@/utils/actionResult';

describe('parseActionResult 边界与字段断言', () => {
  it('空字符串返回 null', () => {
    expect(parseActionResult('')).toBeNull();
    expect(parseActionResult('   ')).toBeNull();
  });

  it('合法对象含 __action__ 字段', () => {
    const parsed = parseActionResult({ __action__: 'repos_imported', ok: true, count: 5 });
    expect(parsed).not.toBeNull();
    expect(parsed?.action).toBe('repos_imported');
    expect(parsed?.ok).toBe(true);
  });

  it('对象无 __action__ 字段返回 null', () => {
    expect(parseActionResult({ foo: 'bar' })).toBeNull();
  });

  it('非对象内容返回 null', () => {
    expect(parseActionResult('plain text')).toBeNull();
    expect(parseActionResult(null)).toBeNull();
    expect(parseActionResult(undefined)).toBeNull();
  });

  it('action 映射到对应 kind', () => {
    const note = parseActionResult({ __action__: 'note_created', ok: true });
    expect(note?.kind).toBe('note');
    const cat = parseActionResult({ __action__: 'category_ensured', ok: true });
    expect(cat?.kind).toBe('category');
  });
});