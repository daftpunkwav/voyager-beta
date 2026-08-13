import { describe, expect, it } from 'vitest';
import { formatTokenCount, formatTokenPercent } from '@/utils/formatTokens';

describe('formatTokenCount', () => {
  it('formats Chinese units', () => {
    expect(formatTokenCount(0)).toBe('0');
    expect(formatTokenCount(1500)).toBe('1.5K');
    expect(formatTokenCount(25_000)).toBe('2.5万');
    expect(formatTokenCount(1_310_000_000)).toBe('13.1亿');
  });
});

describe('formatTokenPercent', () => {
  it('handles zero total', () => {
    expect(formatTokenPercent(10, 0)).toBe('0%');
  });

  it('formats ratio', () => {
    expect(formatTokenPercent(49, 100)).toBe('49%');
    expect(formatTokenPercent(5.5, 100)).toBe('5.5%');
  });
});
