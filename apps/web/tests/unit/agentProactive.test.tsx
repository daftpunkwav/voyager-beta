/** 设置页 Agent 主动触达单测(phase-18):
 *  五键读取/保存走 settings.get_setting/set_setting,非法值不发请求。 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

import { AgentSettingsSection } from '@/components/settings/AgentSettingsSection';
import type { Settings } from '@/api/types';
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
  'agent.network.mode': 'whitelist',
  'agent.network.domains': ['github.com', 'arxiv.org'],
  'agent.workspace.dir': 'workspace',
  'agent.proactive.per_session': 3,
  'agent.proactive.per_day': 10,
  'agent.proactive.follow_up_max': 2,
  'agent.proactive.quiet_start': 23,
  'agent.proactive.quiet_end': 7,
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

const noop = () => Promise.resolve();

function renderSection() {
  render(
    <AgentSettingsSection
      settings={{ agent_code_of_conduct: '', agent_guidelines: [] } as Settings}
      updateSettings={noop}
    />,
  );
}

beforeEach(() => {
  Object.assign(SETTINGS, {
    'agent.style': '热心',
    'agent.memory.retention_days': 90,
    'agent.rounds.max': 20,
    'agent.rounds.tool_max': 40,
    'agent.network.mode': 'whitelist',
    'agent.network.domains': ['github.com', 'arxiv.org'],
    'agent.workspace.dir': 'workspace',
    'agent.proactive.per_session': 3,
    'agent.proactive.per_day': 10,
    'agent.proactive.follow_up_max': 2,
    'agent.proactive.quiet_start': 23,
    'agent.proactive.quiet_end': 7,
  });
  callCapabilityMock.mockReset();
  callCapabilityMock.mockImplementation(backend);
  getApiMock.mockReset();
  useUIStore.setState({ toasts: [] });
});

/** 等 get_setting 草稿填进输入框(挂载是异步的) */
async function waitDraft(label: string, expected: string) {
  await waitFor(() =>
    expect((screen.getByLabelText(label) as HTMLInputElement).value).toBe(expected),
  );
}

describe('主动触达(phase-18)', () => {
  it('挂载时读取五键草稿', async () => {
    renderSection();
    await waitDraft('每会话上限', '3');
    await waitDraft('每日上限', '10');
    await waitDraft('追问链上限', '2');
    await waitDraft('开始', '23');
    await waitDraft('结束', '7');
  });

  it('改每会话上限保存打到 agent.proactive.per_session', async () => {
    renderSection();
    await waitDraft('每会话上限', '3');

    fireEvent.change(screen.getByLabelText('每会话上限'), { target: { value: '5' } });
    fireEvent.blur(screen.getByLabelText('每会话上限'));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.proactive.per_session',
        value: 5,
      }),
    );
  });

  it('追问链超范围 toast 警告,不发请求', async () => {
    renderSection();
    await waitDraft('追问链上限', '2');

    fireEvent.change(screen.getByLabelText('追问链上限'), { target: { value: '6' } });
    fireEvent.blur(screen.getByLabelText('追问链上限'));
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true),
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.proactive.follow_up_max' }),
    );
  });

  it('安静时段小时超范围(24) toast 警告,不发请求', async () => {
    renderSection();
    await waitDraft('开始', '23');

    fireEvent.change(screen.getByLabelText('开始'), { target: { value: '24' } });
    fireEvent.blur(screen.getByLabelText('开始'));
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true),
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.proactive.quiet_start' }),
    );
  });

  it('清空输入不把空串当成 0 提交', async () => {
    renderSection();
    await waitDraft('每会话上限', '3');

    fireEvent.change(screen.getByLabelText('每会话上限'), { target: { value: '' } });
    fireEvent.blur(screen.getByLabelText('每会话上限'));
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true),
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.proactive.per_session' }),
    );
  });
});
