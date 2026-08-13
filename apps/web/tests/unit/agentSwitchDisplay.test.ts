import { describe, expect, it } from 'vitest';
import {
  cleanSwitchReason,
  displaySwitchReason,
} from '@/utils/agentSwitchDisplay';

describe('displaySwitchReason', () => {
  it('falls back to role label', () => {
    expect(displaySwitchReason('', 'mentor')).toBe('深度讲解');
    expect(displaySwitchReason('Hub 调度 mentor', 'mentor')).toBe('深度讲解');
  });

  it('keeps short reason', () => {
    expect(displaySwitchReason('按模块复述级讲解 GPDot', 'mentor')).toBe(
      '按模块复述级讲解 GPDot'
    );
  });

  it('clips long reason at punctuation', () => {
    const long =
      '用户是零基础，需要 mentor 把 GPDot 按每个模块做了什么的复述级深度拆开讲，'
      + '不能用 navigator（不需要独立路线图），也不要一次堆太多概念与术语';
    const out = displaySwitchReason(long, 'mentor', 72);
    expect(out.length).toBeLessThan(long.length);
    expect(out.length).toBeLessThanOrEqual(73);
  });
});

describe('cleanSwitchReason', () => {
  it('collapses whitespace', () => {
    expect(cleanSwitchReason('  a\n\nb  ')).toBe('a b');
  });
});
