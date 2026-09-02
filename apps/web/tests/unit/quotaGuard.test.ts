/** 发送前 token 日配额守卫单测(phase-67):
 *  evaluateQuota 纯函数判定(不限/未达阈值/≥80% warn/已满 block)、
 *  fetchQuotaGuard 软失败(查询失败放行,由后端 metered_llm 兜底)。 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({
  callCapabilityMock: vi.fn(),
}));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import {
  QUOTA_BLOCK_MESSAGE,
  QUOTA_WARN_RATIO,
  evaluateQuota,
  fetchQuotaGuard,
  quotaWarnMessage,
} from '@/bridge/quotaGuard';

beforeEach(() => {
  callCapabilityMock.mockReset();
});

describe('evaluateQuota 纯函数判定', () => {
  it('daily_tokens=0 不限 → allow', () => {
    expect(evaluateQuota({ tokens_used_today: 98765, daily_tokens: 0 })).toEqual({
      action: 'allow',
    });
  });

  it('50/100 未达阈值 → allow', () => {
    expect(evaluateQuota({ tokens_used_today: 50, daily_tokens: 100 })).toEqual({
      action: 'allow',
    });
  });

  it('85/100 ≥80% → warn 且带 ratio', () => {
    expect(evaluateQuota({ tokens_used_today: 85, daily_tokens: 100 })).toEqual({
      action: 'warn',
      ratio: 0.85,
    });
  });

  it('100/100 已满 → block 且带 reason', () => {
    expect(evaluateQuota({ tokens_used_today: 100, daily_tokens: 100 })).toEqual({
      action: 'block',
      reason: QUOTA_BLOCK_MESSAGE,
    });
  });

  it('超过上限(120/100)同样 block', () => {
    expect(evaluateQuota({ tokens_used_today: 120, daily_tokens: 100 }).action).toBe('block');
  });

  it('负数上限视为不限 → allow', () => {
    expect(evaluateQuota({ tokens_used_today: 10, daily_tokens: -1 })).toEqual({
      action: 'allow',
    });
  });

  it('阈值常量为 0.8(发送前提醒,与用量页 0.9 展示阈值刻意不同)', () => {
    expect(QUOTA_WARN_RATIO).toBe(0.8);
  });
});

describe('quotaWarnMessage 文案', () => {
  it('带百分比四舍五入', () => {
    expect(quotaWarnMessage(0.85)).toContain('85%');
    expect(quotaWarnMessage(0.856)).toContain('86%');
  });
});

describe('fetchQuotaGuard', () => {
  it('读 get_resource_quota 并判定;已满 → block', async () => {
    callCapabilityMock.mockResolvedValue({ tokens_used_today: 5000, daily_tokens: 5000 });
    await expect(fetchQuotaGuard()).resolves.toEqual({
      action: 'block',
      reason: QUOTA_BLOCK_MESSAGE,
    });
    expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'get_resource_quota', {});
  });

  it('查询失败软失败放行 → allow,不 throw', async () => {
    callCapabilityMock.mockRejectedValue(new Error('backend down'));
    await expect(fetchQuotaGuard()).resolves.toEqual({ action: 'allow' });
  });
});
