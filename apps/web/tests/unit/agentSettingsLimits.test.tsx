/** 设置页 Agent 轮数/网络/工作目录单测(phase-10):
 *  get_setting mock 严格按 key 分支(记忆区同页共存),改值打到正确 settings key,
 *  非法轮数 / URL 形态域名 / 含 .. 目录不发请求。 */

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

function renderSection() {
  render(<AgentSettingsSection />);
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
    expect((screen.getByLabelText(label) as HTMLInputElement).value).toBe(expected),
  );
}

describe('轮数上限(phase-10)', () => {
  it('挂载时读取草稿;失焦保存打到 agent.rounds.max', async () => {
    renderSection();
    await waitDraft('ReAct 轮数上限', '20');

    fireEvent.change(screen.getByLabelText('ReAct 轮数上限'), { target: { value: '25' } });
    fireEvent.blur(screen.getByLabelText('ReAct 轮数上限'));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.rounds.max',
        value: 25,
      }),
    );
  });

  it('范围外轮数 toast 警告,不发请求', async () => {
    renderSection();
    await waitDraft('工具调用轮数上限', '40');

    fireEvent.change(screen.getByLabelText('工具调用轮数上限'), { target: { value: '999' } });
    fireEvent.blur(screen.getByLabelText('工具调用轮数上限'));
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true),
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.rounds.tool_max' }),
    );
  });
});

describe('网络权限(phase-10)', () => {
  it('切档位保存为后端枚举值(off|whitelist|all)', async () => {
    renderSection();
    await waitDraft('ReAct 轮数上限', '20'); // 页面就绪

    fireEvent.click(screen.getByRole('button', { name: '网络权限模式' }));
    fireEvent.click(screen.getByRole('option', { name: '全开' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.network.mode',
        value: 'all',
      }),
    );
  });

  it('白名单域名一行一个:trim/去空行后保存为 JSON 数组', async () => {
    renderSection();
    await waitDraft('ReAct 轮数上限', '20');

    const box = screen.getByLabelText('白名单域名') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'github.com\n pypi.org \n\n' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.network.domains',
        value: ['github.com', 'pypi.org'],
      }),
    );
  });

  it('整段 URL 形态的域名拒收,不发请求', async () => {
    renderSection();
    await waitDraft('ReAct 轮数上限', '20');

    const box = screen.getByLabelText('白名单域名') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'https://github.com' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true),
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.network.domains' }),
    );
  });
});

describe('工作目录(phase-10)', () => {
  it('保存打到 agent.workspace.dir', async () => {
    renderSection();
    await waitDraft('工作目录', 'workspace');

    fireEvent.change(screen.getByLabelText('工作目录'), { target: { value: 'ws2' } });
    fireEvent.blur(screen.getByLabelText('工作目录'));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.workspace.dir',
        value: 'ws2',
      }),
    );
  });

  it('含 .. 段的路径拒收,不发请求', async () => {
    renderSection();
    await waitDraft('工作目录', 'workspace');

    fireEvent.change(screen.getByLabelText('工作目录'), { target: { value: '../evil' } });
    fireEvent.blur(screen.getByLabelText('工作目录'));
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true),
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.workspace.dir' }),
    );
  });
});
