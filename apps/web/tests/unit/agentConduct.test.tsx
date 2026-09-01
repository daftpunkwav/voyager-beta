/** 设置页通用/分 Agent 行为准则单测(phase-29):
 *  草稿来自 settings.get_setting,保存打到 settings.set_setting(agent.conduct / agent.guidelines),
 *  不再走 settingsStore.updateSettings(不调 getApi);分 Agent 保存 merge 当前 tab,空串删键。 */

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
  'agent.conduct': '回答简洁',
  'agent.guidelines': { orchestrator: '先确认再改代码' },
  'agent.memory.retention_days': 90,
  'agent.rounds.max': 20,
  'agent.rounds.tool_max': 40,
  'agent.network.mode': 'whitelist',
  'agent.network.domains': ['github.com'],
  'agent.workspace.dir': 'workspace',
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
  Object.assign(SETTINGS, {
    'agent.style': '热心',
    'agent.conduct': '回答简洁',
    'agent.guidelines': { orchestrator: '先确认再改代码' },
    'agent.memory.retention_days': 90,
    'agent.rounds.max': 20,
    'agent.rounds.tool_max': 40,
    'agent.network.mode': 'whitelist',
    'agent.network.domains': ['github.com'],
    'agent.workspace.dir': 'workspace',
  });
  callCapabilityMock.mockReset();
  callCapabilityMock.mockImplementation(backend);
  getApiMock.mockReset();
  useUIStore.setState({ toasts: [] });
});

describe('通用行为准则(phase-29)', () => {
  it('挂载后草稿来自 get_setting(agent.conduct)', async () => {
    renderSection();
    const box = (await screen.findByLabelText('通用行为准则')) as HTMLTextAreaElement;
    expect(box.value).toBe('回答简洁');
  });

  it('保存打 set_setting {key: agent.conduct},不调 getApi', async () => {
    renderSection();
    const box = (await screen.findByLabelText('通用行为准则')) as HTMLTextAreaElement;

    fireEvent.change(box, { target: { value: '回答简洁,不用 emoji' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.conduct',
        value: '回答简洁,不用 emoji',
      }),
    );
    expect(getApiMock).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'success')).toBe(true),
    );
  });

  it('清空后保存写回空串', async () => {
    renderSection();
    const box = (await screen.findByLabelText('通用行为准则')) as HTMLTextAreaElement;

    fireEvent.change(box, { target: { value: '' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.conduct',
        value: '',
      }),
    );
  });
});

describe('分 Agent 行为准则(phase-29)', () => {
  it('挂载后草稿来自 get_setting(agent.guidelines) 的对应人格键', async () => {
    renderSection();
    const box = (await screen.findByLabelText('Lucien 行为准则')) as HTMLTextAreaElement;
    expect(box.value).toBe('先确认再改代码');
  });

  it('保存 merge 当前 tab 的人格 id,其余键原样保留', async () => {
    renderSection();
    await waitFor(() =>
      expect((screen.getByLabelText('Lucien 行为准则') as HTMLTextAreaElement).value)
        .toBe('先确认再改代码'),
    );

    fireEvent.click(screen.getByRole('tab', { name: 'Iris' }));
    const box = screen.getByLabelText('Iris 行为准则') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: '只读不改' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.guidelines',
        value: { orchestrator: '先确认再改代码', recon: '只读不改' },
      }),
    );
  });

  it('清空草稿保存后从对象删键', async () => {
    renderSection();
    const box = (await screen.findByLabelText('Lucien 行为准则')) as HTMLTextAreaElement;

    fireEvent.change(box, { target: { value: '' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.guidelines',
        value: {},
      }),
    );
  });
});

describe('说话风格搬家后照常(phase-29)', () => {
  it('切档位保存打到 agent.style', async () => {
    renderSection();
    await screen.findByLabelText('通用行为准则'); // 页面就绪

    fireEvent.click(screen.getByRole('button', { name: '全局说话风格' }));
    fireEvent.click(screen.getByRole('option', { name: '毒舌' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.style',
        value: '毒舌',
      }),
    );
  });
});
