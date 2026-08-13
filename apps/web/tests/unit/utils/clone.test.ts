import { describe, expect, it } from 'vitest';
import { deepClone } from '@/utils/clone';

describe('deepClone', () => {
  it('clones primitives by reference equality', () => {
    const n = 42;
    expect(deepClone(n)).toBe(42);
  });

  it('clones plain objects without sharing references', () => {
    const src = { a: 1, nested: { b: 2 } };
    const dst = deepClone(src);
    expect(dst).toEqual(src);
    expect(dst).not.toBe(src);
    expect(dst.nested).not.toBe(src.nested);
  });

  it('clones arrays without sharing references', () => {
    const src = [{ a: 1 }, { b: 2 }];
    const dst = deepClone(src);
    expect(dst).toEqual(src);
    expect(dst).not.toBe(src);
    expect(dst[0]).not.toBe(src[0]);
  });

  it('clones dates (structuredClone preserves them)', () => {
    const src = { d: new Date('2026-01-01T00:00:00Z') };
    const dst = deepClone(src);
    expect(dst.d).toBeInstanceOf(Date);
    expect(dst.d.getTime()).toBe(src.d.getTime());
  });
});
