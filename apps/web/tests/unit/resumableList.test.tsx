/** Phase-70 A 单测:团队页可恢复任务列表。
 *  列表渲染、继续(resume_run continue_run=true)、放弃(confirm + abandon)、
 *  空态与加载失败重试。 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

// 保留真实 ServiceError(失败分支 error toast 走 extractErrorMessage)
vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import { ResumableList } from '@/pages/team/ResumableList';
import { useUIStore } from '@/stores/uiStore';

/** 有状态 mock:abandon / resume 成功后 items 清空(模拟后端删盘 / 续跑完) */
let items: Array<Record<string, unknown>> = [];

function backend(_domain: string, name: string, args: Record<string, unknown>) {
  switch (name) {
    case 'list_resumable_checkpoints':
      return Promise.resolve({ items });
    case 'resume_run':
    case 'abandon_resumable_checkpoint':
      items = items.filter((i) => i.run_id !== args.run_id);
      return Promise.resolve(name === 'resume_run'
        ? { resumed: 'inst1', run_id: args.run_id, status: 'running', continuing: true }
        : { abandoned: args.run_id });
    default:
      return Promise.resolve({});
  }
}

function sampleItem(overrides: Record<string, unknown> = {}) {
  return {
    run_id: 'runresum001',
    status: 'paused',
    goal: '索引整个仓库并产出清单,清单要包含每个模块的职责说明',
    instance_name: '侦察兵',
    started_ts: Math.floor(Date.now() / 1000) - 120,
    last_step: '第 1 轮:已列目录',
    mode: 'react',
    ...overrides,
  };
}

beforeEach(() => {
  items = [];
  callCapabilityMock.mockReset();
  callCapabilityMock.mockImplementation(backend);
  useUIStore.setState({ toasts: [] });
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

describe('可恢复任务列表(phase-70 A)', () => {
  it('渲染条目:名称 / goal 截断 / last_step / run_id', async () => {
    items = [sampleItem()];
    render(<ResumableList />);
    expect(await screen.findByText('侦察兵')).toBeTruthy();
    // goal 截断到 80 字符内并带省略号(此处 30 字内不截断,完整显示)
    expect(screen.getByText(/索引整个仓库并产出清单/)).toBeTruthy();
    expect(screen.getByText(/当前:第 1 轮/)).toBeTruthy();
    expect(screen.getByText(/runresum001/)).toBeTruthy();
    expect(screen.getByText(/分钟前/)).toBeTruthy();
  });

  it('点继续:resume_run(continue_run=true) + success toast + 刷新后条目消失', async () => {
    items = [sampleItem()];
    render(<ResumableList />);
    fireEvent.click(await screen.findByRole('button', { name: '继续' }));

    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'resume_run', {
        run_id: 'runresum001',
        continue_run: true,
      }),
    );
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'success' && t.message.includes('已续跑 侦察兵'))).toBe(true),
    );
    await waitFor(() => expect(screen.queryByText('侦察兵')).toBeNull());
    expect(screen.getByText('暂无可恢复任务')).toBeTruthy();
  });

  it('点放弃:确认后调 abandon_resumable_checkpoint + toast + 条目消失', async () => {
    items = [sampleItem()];
    render(<ResumableList />);
    fireEvent.click(await screen.findByRole('button', { name: '放弃' }));

    expect(window.confirm).toHaveBeenCalled();
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'abandon_resumable_checkpoint', {
        run_id: 'runresum001',
      }),
    );
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'success' && t.message.includes('已放弃 侦察兵'))).toBe(true),
    );
    await waitFor(() => expect(screen.queryByText('侦察兵')).toBeNull());
  });

  it('status=running:继续置灰带提示(phase-71 E),放弃仍可用', async () => {
    items = [sampleItem({ status: 'running' })];
    render(<ResumableList />);
    const btn = await screen.findByRole('button', { name: '继续' });
    expect(btn.hasAttribute('disabled')).toBe(true);
    expect(btn.getAttribute('title')).toContain('仍在运行中');
    // 置灰按钮点击不触发 resume_run
    fireEvent.click(btn);
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'agent', 'resume_run', expect.anything(),
    );
    // 放弃不受影响(70 语义:停实例 + 删盘)
    fireEvent.click(screen.getByRole('button', { name: '放弃' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith(
        'agent', 'abandon_resumable_checkpoint', { run_id: 'runresum001' },
      ),
    );
  });

  it('放弃确认弹窗点取消:不发请求', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    items = [sampleItem()];
    render(<ResumableList />);
    fireEvent.click(await screen.findByRole('button', { name: '放弃' }));

    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'agent', 'abandon_resumable_checkpoint', expect.anything(),
    );
    expect(screen.getByText('侦察兵')).toBeTruthy();
  });

  it('空 items:空态「暂无可恢复任务」', async () => {
    render(<ResumableList />);
    expect(await screen.findByText('暂无可恢复任务')).toBeTruthy();
  });

  it('加载失败:错误态 + 重试恢复列表', async () => {
    callCapabilityMock.mockRejectedValue(new Error('后端失联'));
    render(<ResumableList />);
    expect(await screen.findByText('可恢复任务加载失败')).toBeTruthy();

    callCapabilityMock.mockImplementation(backend);
    items = [sampleItem()];
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    expect(await screen.findByText('侦察兵')).toBeTruthy();
  });
});
