import { describe, expect, it } from 'vitest';
import { formatNumber, langCssClass, splitRepoName } from '@/utils/format';

describe('formatNumber', () => {
  it('returns 0 for null/undefined', () => {
    expect(formatNumber(null)).toBe('0');
    expect(formatNumber(undefined)).toBe('0');
  });

  it('renders integers as-is below 10k', () => {
    expect(formatNumber(0)).toBe('0');
    expect(formatNumber(123)).toBe('123');
    expect(formatNumber(9999)).toBe('9999');
  });

  it('renders 10k+ as floored kilo', () => {
    expect(formatNumber(10000)).toBe('10k');
    expect(formatNumber(220000)).toBe('220k');
  });
});

describe('splitRepoName', () => {
  it('splits owner/repo', () => {
    expect(splitRepoName('facebook/react')).toEqual({ owner: 'facebook', repo: 'react' });
  });

  it('returns empty strings for malformed input', () => {
    expect(splitRepoName('just-one')).toEqual({ owner: 'just-one', repo: '' });
    expect(splitRepoName('')).toEqual({ owner: '', repo: '' });
  });
});

describe('langCssClass', () => {
  it('returns lang-other for empty', () => {
    expect(langCssClass(undefined)).toBe('lang-other');
  });

  it('normalises TS/JS aliases', () => {
    expect(langCssClass('TypeScript')).toBe('lang-ts');
    expect(langCssClass('ts')).toBe('lang-ts');
    expect(langCssClass('JavaScript')).toBe('lang-js');
    expect(langCssClass('js')).toBe('lang-js');
  });

  it('lowercases and sanitises unknown languages', () => {
    expect(langCssClass('Kotlin')).toBe('lang-kotlin');
  });
});
