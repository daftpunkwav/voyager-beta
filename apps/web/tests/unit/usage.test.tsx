/** 用量页:汇总卡数字渲染、按模型表行、时间窗切换传参、降级态。 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UsagePage } from '@/pages/usage/UsagePage';
import { useUsageStore } from '@/pages/usage/usageStore';

const callMock = vi.fn();

vi.mock('@/bridge/client', () => ({
  callCapability: (...args: unknown[]) => callMock(...args),
  ServiceError: class extends Error {
    code = '';
    hint = '';
  },
}));

const STATS = {
  days: 30,
  input_tokens: 1234,
  output_tokens: 5678,
  calls: 9,
  by_model: [
    { model: 'kimi-k2', input: 1000, output: 5000, calls: 7 },
    { model: 'gpt-test', input: 234, output: 678, calls: 2 },
  ],
};

beforeEach(() => {
  callMock.mockReset();
  useUsageStore.setState({ days: 30, stats: null, loading: false, error: null });
});

describe('UsagePage 渲染', () => {
  it('汇总卡数字与 by_model 表行;占比条 title 带百分比', async () => {
    callMock.mockResolvedValue(STATS);
    render(<UsagePage />);
    await waitFor(() => expect(screen.getByText('1234')).toBeTruthy());
    expect(screen.getByText('5678')).toBeTruthy();
    expect(screen.getByText('9')).toBeTruthy();
    expect(screen.getByText('kimi-k2')).toBeTruthy();
    expect(screen.getByText('gpt-test')).toBeTruthy();
    expect(screen.getByTitle(/kimi-k2:7 次\(78%\)/)).toBeTruthy();
    expect(callMock).toHaveBeenCalledWith('llm', 'get_usage_stats', { days: 30 });
  });

  it('大数字用 k 缩写', async () => {
    callMock.mockResolvedValue({
      ...STATS, input_tokens: 123456, output_tokens: 2_000_000, calls: 1234,
    });
    render(<UsagePage />);
    await waitFor(() => expect(screen.getByText('123.5k')).toBeTruthy());
    expect(screen.getByText('2.0M')).toBeTruthy();
  });

  it('切换 7 天 -> 以 days=7 重新拉取', async () => {
    callMock.mockResolvedValue(STATS);
    render(<UsagePage />);
    await waitFor(() => expect(screen.getByText('kimi-k2')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /近 7 天/ }));
    await waitFor(() =>
      expect(callMock).toHaveBeenLastCalledWith('llm', 'get_usage_stats', { days: 7 }),
    );
  });

  it('空数据给引导文案', async () => {
    callMock.mockResolvedValue({
      days: 30, input_tokens: 0, output_tokens: 0, calls: 0, by_model: [],
    });
    render(<UsagePage />);
    await waitFor(() => expect(screen.getByText(/还没有用量/)).toBeTruthy());
  });

  it('llm 服务不可用走降级态(错误码 + 重试)', async () => {
    callMock.mockRejectedValue(Object.assign(new Error('llm 服务不可用'), { code: 'LLM.UNAVAILABLE' }));
    render(<UsagePage />);
    await waitFor(() => expect(screen.getByText(/用量数据不可用/)).toBeTruthy());
    expect(screen.getByText('LLM.UNAVAILABLE')).toBeTruthy();
    expect(screen.getByRole('button', { name: '重试' })).toBeTruthy();
  });
});
