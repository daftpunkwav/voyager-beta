/** 用量页布局单测(phase-65):「今日 token 配额」块独立于 llm 历史统计——
 *  getLlmUsage 失败 / 加载中时配额块仍可见,不被父级空态或加载态连坐。 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock, getApiMock } = vi.hoisted(() => ({
  callCapabilityMock: vi.fn(),
  getApiMock: vi.fn(),
}));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

vi.mock('@/api/client', () => ({ getApi: getApiMock }));

import { LlmUsageDashboard } from '@/components/usage/LlmUsageDashboard';

function renderDashboard() {
  // retry 关掉:失败用例不等指数退避
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LlmUsageDashboard />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  callCapabilityMock.mockReset();
  getApiMock.mockReset();
  getApiMock.mockReturnValue({ getLlmUsage: vi.fn() });
});

describe('用量页布局:配额块独立渲染(phase-65)', () => {
  it('getLlmUsage 失败时仍显示今日 token 配额块', async () => {
    callCapabilityMock.mockResolvedValue({ tokens_used_today: 1200, daily_tokens: 5000 });
    getApiMock.mockReturnValue({
      getLlmUsage: vi.fn().mockRejectedValue(new Error('boom')),
    });
    renderDashboard();

    // 配额块(自有 query 成功)可见
    expect(await screen.findByText(/已用 1\.2K/)).toBeInTheDocument();
    expect(screen.getByText('今日 token 配额')).toBeInTheDocument();
    // llm 历史统计走自己的空态,不覆盖配额块
    expect(await screen.findByText('用量统计服务暂不可用')).toBeInTheDocument();
  });

  it('getLlmUsage 加载中时配额块已渲染,不被 Spinner 盖住', async () => {
    callCapabilityMock.mockResolvedValue({ tokens_used_today: 120, daily_tokens: 0 });
    getApiMock.mockReturnValue({
      getLlmUsage: vi.fn().mockReturnValue(new Promise(() => {})), // 永不落定
    });
    renderDashboard();

    expect(await screen.findByText('今日 token 配额')).toBeInTheDocument();
    expect(screen.getByText('加载用量统计中…')).toBeInTheDocument();
  });
});
