import { describe, expect, it } from 'vitest';
import { userInitials } from '@/utils/user';

describe('userInitials', () => {
  it('returns first 2 chars uppercased for known names', () => {
    expect(userInitials('zhang.jie')).toBe('ZH');
    expect(userInitials('te')).toBe('TE');
  });

  it('returns G (guest) for null/undefined/empty', () => {
    expect(userInitials(null)).toBe('G');
    expect(userInitials(undefined)).toBe('G');
    expect(userInitials('')).toBe('G');
  });

  it('handles names that are exactly 1 char', () => {
    expect(userInitials('a')).toBe('A');
  });
});