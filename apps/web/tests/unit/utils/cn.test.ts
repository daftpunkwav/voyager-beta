import { describe, expect, it } from 'vitest';
import { cn } from '@/utils/cn';

describe('cn', () => {
  it('joins truthy class names', () => {
    expect(cn('a', 'b', 'c')).toBe('a b c');
  });

  it('skips falsy values', () => {
    expect(cn('a', false, null, undefined, 0, '', 'b')).toBe('a b');
  });

  it('returns empty string when no inputs', () => {
    expect(cn()).toBe('');
  });

  it('flattens nested arrays', () => {
    expect(cn(['a', 'b'], 'c', ['d'])).toBe('a b c d');
  });
});
