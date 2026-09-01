/** 设置页 Agent token 日配额单测(phase-61):
 *  挂载读取草稿、保存打到 agent.resource.daily_tokens、
 *  超范围拒收不发请求、0=不限 是合法值。 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({
  callCapabilityMock: vi.fn(),
}));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

vi.mock('@/api/client', () => ({ getApi: vi.fn() }));

import { AgentSettingsSection } from '@/components/settings/AgentSettingsSection';
import { useUIStore } from '@/stores/uiStore';

const SNAPSHOT = {
  profile: { summary: '', items: [] },
  episodic: { recent: [], shown: 0 },
  semantic: { recent: [], shown: 0 },
  working: { size: 0 },
  retention_days: 90,
  purged_episodic: 0,
};

/** 按 key 返回的设置库;set_setting 会写回,用例间重置 */
const SETTINGS: Record<string, unknown> = {
  'agent.style': '热心',
  'agent.memory.retention_days': 90,
  'agent.rounds.max': 20,
  'agent.rounds.tool_max': 40,
  'agent.resource.daily_tokens': 500000,
  'agent.network.mode': 'whitelist',
  'agent.network.domains': ['github.com'],
  'agent.workspace.dir': 'workspace',
  'agent.app.allowed': ['*'],
  'agent.app.denied': [],
};

function backend(_domain: string, name: string, args: Record<string, unknown>) {
  switch (name) {
    case 'get_memory':
      return Promise.resolve(SNAPSHOT);
    case 'get_setting':
      return Promise.resolve({ value: SETTINGS[String(args.key)] });
    case 'set_setting':
      SETTINGS[String(args.key)] = args.value;
      return Promise.resolve({ value: args.value });
    default:
      return Promise.resolve({});
  }
}

function renderSection() {
  render(<AgentSettingsSection />);
}

beforeEach(() => {
  Object.assign(SETTINGS, { 'agent.resource.daily_tokens': 500000 });
  callCapabilityMock.mockReset();
  callCapabilityMock.mockImplementation(backend);
  useUIStore.setState({ toasts: [] });
});

/** 等 get_setting 草稿填进输入框(挂载是异步的) */
async function waitDraft(expected: string) {
  await waitFor(() =>
    expect((screen.getByLabelText('Token 日配额') as HTMLInputElement).value).toBe(expected),
  );
}

describe('token 日配额(phase-61)', () => {
  it('挂载时读取草稿', async () => {
    renderSection();
    await waitDraft('500000');
  });

  it('保存打到 agent.resource.daily_tokens 且为整数', async () => {
    renderSection();
    await waitDraft('500000');

    fireEvent.change(screen.getByLabelText('Token 日配额'), { target: { value: '250000' } });
    fireEvent.blur(screen.getByLabelText('Token 日配额'));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.resource.daily_tokens',
        value: 250000,
      }),
    );
  });

  it('超出上限(10000000)拒收,不发请求', async () => {
    renderSection();
    await waitDraft('500000');

    fireEvent.change(screen.getByLabelText('Token 日配额'), { target: { value: '10000001' } });
    fireEvent.blur(screen.getByLabelText('Token 日配额'));
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true),
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.resource.daily_tokens' }),
    );
  });

  it('0 合法(表示不限),正常发出保存', async () => {
    renderSection();
    await waitDraft('500000');

    fireEvent.change(screen.getByLabelText('Token 日配额'), { target: { value: '0' } });
    fireEvent.blur(screen.getByLabelText('Token 日配额'));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.resource.daily_tokens',
        value: 0,
      }),
    );
  });

  it('非整数(负数)拒收,不发请求', async () => {
    renderSection();
    await waitDraft('500000');

    fireEvent.change(screen.getByLabelText('Token 日配额'), { target: { value: '-5' } });
    fireEvent.blur(screen.getByLabelText('Token 日配额'));
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true),
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.resource.daily_tokens' }),
    );
  });

  it('清空输入框(空串)拒收,不发请求——防静默存 0=不限', async () => {
    renderSection();
    await waitDraft('500000');

    fireEvent.change(screen.getByLabelText('Token 日配额'), { target: { value: '' } });
    fireEvent.blur(screen.getByLabelText('Token 日配额'));
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true),
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.resource.daily_tokens' }),
    );
  });
});
