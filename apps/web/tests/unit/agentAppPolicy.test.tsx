/** 设置页 Agent 应用内能力白名单单测(phase-19):
 *  允许/拒绝名单读取/保存走 settings.get_setting/set_setting,
 *  空允许名单 / URL 形态 / 含 .. 不发请求。 */

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
    'agent.app.allowed': ['*'],
    'agent.app.denied': [],
  });
  callCapabilityMock.mockReset();
  callCapabilityMock.mockImplementation(backend);
  getApiMock.mockReset();
  useUIStore.setState({ toasts: [] });
});

/** 等 get_setting 草稿填进输入框(挂载是异步的) */
async function waitDraft(label: string, expected: string) {
  await waitFor(() =>
    expect((screen.getByLabelText(label) as HTMLTextAreaElement).value).toBe(expected),
  );
}

describe('应用内能力白名单(phase-19)', () => {
  it('挂载时读取默认允许 * / 拒绝空', async () => {
    renderSection();
    await waitDraft('应用内能力允许名单', '*');
    await waitDraft('应用内能力拒绝名单', '');
  });

  it('改允许名单保存打到 agent.app.allowed(数组)', async () => {
    renderSection();
    await waitDraft('应用内能力允许名单', '*');

    const box = screen.getByLabelText('应用内能力允许名单') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'notes__create_note\ngraph__search' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.app.allowed',
        value: ['notes__create_note', 'graph__search'],
      }),
    );
  });

  it('改拒绝名单保存打到 agent.app.denied', async () => {
    renderSection();
    await waitDraft('应用内能力允许名单', '*');

    const box = screen.getByLabelText('应用内能力拒绝名单') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'notes__delete_note\ngraph__*' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.app.denied',
        value: ['notes__delete_note', 'graph__*'],
      }),
    );
  });

  it('清空允许名单 toast 警告,不发请求', async () => {
    renderSection();
    await waitDraft('应用内能力允许名单', '*');

    const box = screen.getByLabelText('应用内能力允许名单') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: '' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true),
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.app.allowed' }),
    );
  });

  it('URL 形态拒收,不发请求', async () => {
    renderSection();
    await waitDraft('应用内能力允许名单', '*');

    const box = screen.getByLabelText('应用内能力允许名单') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'https://github.com' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true),
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.app.allowed' }),
    );
  });

  it('含 .. 拒收,不发请求', async () => {
    renderSection();
    await waitDraft('应用内能力允许名单', '*');

    const box = screen.getByLabelText('应用内能力允许名单') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'notes__../evil' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true),
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.app.allowed' }),
    );
  });
});
