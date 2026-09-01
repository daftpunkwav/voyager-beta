/** 设置页记忆区单测(phase-08):摘要可见、清空全部走 agent.clear_memory(zone=all)、
 *  不再调用 getApi()(旧 clearUserMemory→recall_memory 死链已移除)。 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock, getApiMock } = vi.hoisted(() => ({
  callCapabilityMock: vi.fn(),
  getApiMock: vi.fn(),
}));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

// getApi 一旦被调用就让测试失败:记忆区必须走 callCapability
vi.mock('@/api/client', () => ({ getApi: getApiMock }));

import { AgentSettingsSection } from '@/components/settings/AgentSettingsSection';
import { useUIStore } from '@/stores/uiStore';

const SNAPSHOT = {
  profile: { summary: '- 语言偏好: 中文\n- 学习目标: langgraph', items: [{ key: '语言偏好', value: '中文' }] },
  episodic: { recent: [{ id: 1, ts: 1756500000, kind: 'consider', summary: '用户在看 langgraph' }], shown: 1 },
  semantic: { recent: [], shown: 0 },
  working: { size: 3 },
  retention_days: 90,
  purged_episodic: 0,
};

function backend(_domain: string, name: string, args: Record<string, unknown>) {
  switch (name) {
    case 'get_memory':
      return Promise.resolve(SNAPSHOT);
    case 'get_setting':
      return Promise.resolve({ value: args.key === 'agent.memory.retention_days' ? 90 : '热心' });
    case 'set_setting':
      return Promise.resolve({ value: args.value });
    case 'clear_memory':
      return Promise.resolve({ zone: args.zone, cleared: { [String(args.zone)]: 4 } });
    case 'set_profile':
    case 'delete_profile':
      return Promise.resolve({ ok: true });
    default:
      return Promise.resolve({});
  }
}

function renderSection() {
  render(<AgentSettingsSection />);
}

beforeEach(() => {
  callCapabilityMock.mockReset();
  callCapabilityMock.mockImplementation(backend);
  getApiMock.mockReset();
  useUIStore.setState({ toasts: [] });
});

describe('设置页记忆区(phase-08)', () => {
  it('渲染画像摘要与键值(不调 getApi)', async () => {
    renderSection();
    await waitFor(() => expect(screen.getByText(/语言偏好: 中文/)).toBeTruthy());
    expect(screen.getByText('中文')).toBeTruthy();
    expect(getApiMock).not.toHaveBeenCalled();
  });

  it('点清空全部弹确认,确认后调 clear_memory 且 zone=all', async () => {
    renderSection();
    await waitFor(() => expect(screen.getByText(/语言偏好: 中文/)).toBeTruthy());

    fireEvent.click(screen.getByTestId('clear-memory-all-btn'));
    const dialog = screen.getByRole('dialog');
    // 确认文案写明时间线/笔记/项目保留
    expect(within(dialog).getByText(/对话时间线、笔记与项目会保留/)).toBeTruthy();
    expect(callCapabilityMock).not.toHaveBeenCalledWith('agent', 'clear_memory', { zone: 'all' });

    // 用 within(dialog) 限定:页面里工作记忆区也有同名"清空"按钮
    fireEvent.click(within(dialog).getByRole('button', { name: '清空' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'clear_memory', { zone: 'all' }),
    );
    await waitFor(() => expect(useUIStore.getState().toasts.some((t) => t.type === 'success')).toBe(true));
  });

  it('删除画像键调 delete_profile,成功后重拉 get_memory', async () => {
    renderSection();
    await waitFor(() => expect(screen.getByText('中文')).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: '删除' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'delete_profile', { key: '语言偏好' }),
    );
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'get_memory', {}),
    );
  });

  it('保留天数读写走 settings.set_setting / get_setting', async () => {
    renderSection();
    const input = await screen.findByLabelText('情节记忆保留天数');
    expect((input as HTMLInputElement).value).toBe('90');

    fireEvent.change(input, { target: { value: '30' } });
    fireEvent.blur(input);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.memory.retention_days',
        value: 30,
      }),
    );
  });
});
