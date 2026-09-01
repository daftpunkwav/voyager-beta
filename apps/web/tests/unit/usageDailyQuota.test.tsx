/** 用量页「今日 token 配额」单测(phase-63):
 *  挂载读 agent.get_resource_quota、已用/上限展示、0=不限不画进度条、
 *  失败出错误态不崩、达到上限进度条转 warning。 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({
  callCapabilityMock: vi.fn(),
}));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import { DailyTokenQuotaCard } from '@/components/usage/DailyTokenQuotaCard';

function renderCard() {
  // retry 关掉：失败用例不等指数退避
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <DailyTokenQuotaCard />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  callCapabilityMock.mockReset();
});

describe('用量页今日 token 配额(phase-63)', () => {
  it('显示已用与上限(1200/5000),画进度条', async () => {
    callCapabilityMock.mockResolvedValue({ tokens_used_today: 1200, daily_tokens: 5000 });
    renderCard();

    expect(await screen.findByText(/已用 1\.2K/)).toBeInTheDocument();
    expect(screen.getByText(/上限 5\.0K/)).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '24');
    expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'get_resource_quota', {});
  });

  it('daily_tokens=0 显示「不限」,不画假进度条', async () => {
    callCapabilityMock.mockResolvedValue({ tokens_used_today: 500, daily_tokens: 0 });
    renderCard();

    expect(await screen.findByText(/上限 不限/)).toBeInTheDocument();
    expect(screen.getByText(/未设上限，不计进度/)).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });

  it('capability 失败出错误态与重试,不 throw', async () => {
    callCapabilityMock.mockRejectedValue(new Error('boom'));
    renderCard();

    expect(await screen.findByText(/配额读取失败/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument();
  });

  it('用量达到上限时进度条 100% 且转 warning', async () => {
    callCapabilityMock.mockResolvedValue({ tokens_used_today: 5000, daily_tokens: 5000 });
    renderCard();

    const bar = await screen.findByRole('progressbar');
    await waitFor(() => expect(bar).toHaveAttribute('aria-valuenow', '100'));
    expect(bar.className).toContain('is-warning');
  });
});
