/** 设置页插件块单测(phase-72):挂载打 list_plugins、渲染名称/版本/批准状态/contains、
 *  批准/撤销打到 set_plugin_approval 且成功/失败 toast;不调 getApi()。 */

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

/** 按 key 返回的设置库(与既有设置页单测同法,避免连带别的块失败) */
const SETTINGS: Record<string, unknown> = {
  'agent.style': '热心',
  'agent.memory.retention_days': 90,
  'agent.rounds.max': 20,
  'agent.rounds.tool_max': 40,
  'agent.network.mode': 'whitelist',
  'agent.network.domains': ['github.com'],
  'agent.workspace.dir': 'workspace',
};

/** list_plugins 的样例:未批准、带 skill/hook/MCP 声明 */
const PLUGIN = {
  name: 'example',
  version: '0.1.0',
  description: '最小插件示例',
  approved: false,
  permissions: { scopes: ['notes.write'], network: 'off', fs: 'none' },
  contains: { skills: 1, hooks: 1, mcp: true },
  path: 'example',
};

function backend(overrides: Record<string, unknown> = {}, failList = false) {
  return (_domain: string, name: string, args: Record<string, unknown>) => {
    switch (name) {
      case 'list_plugins':
        return failList
          ? Promise.reject(new Error('boom'))
          : Promise.resolve({ items: overrides.items ?? [{ ...PLUGIN, ...overrides.plugin }] });
      case 'set_plugin_approval':
        return Promise.resolve({
          name: args.name,
          approved: args.approved,
          loaded: { skills: ['daily-note'], hooks: 0, mcp_registered: 1, mcp_skipped: false },
        });
      case 'get_memory':
        return Promise.resolve(SNAPSHOT);
      case 'get_setting':
        return Promise.resolve({ value: SETTINGS[String(args.key)] });
      default:
        return Promise.resolve({});
    }
  };
}

function renderSection(impl: ReturnType<typeof backend>) {
  callCapabilityMock.mockImplementation(impl);
  render(<AgentSettingsSection />);
}

const toastTexts = () => useUIStore.getState().toasts.map((t) => t.message);

beforeEach(() => {
  callCapabilityMock.mockReset();
  getApiMock.mockReset();
  useUIStore.setState({ toasts: [] });
});

describe('设置页插件块(phase-72)', () => {
  it('挂载打 list_plugins,渲染名称/版本/描述/未批准/contains;不调 getApi()', async () => {
    renderSection(backend());
    await waitFor(() => expect(screen.getByText('example v0.1.0')).toBeTruthy());
    expect(screen.getByText('最小插件示例')).toBeTruthy();
    expect(screen.getByText(/未批准 · notes.write/)).toBeTruthy();
    expect(screen.getByText(/技能 1 · 钩子 1 · MCP 配置/)).toBeTruthy();
    expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'list_plugins', {});
    expect(getApiMock).not.toHaveBeenCalled();
  });

  it('空清单显示放置指引', async () => {
    renderSection(backend({ items: [] }));
    await waitFor(() => expect(screen.getByText(/还没有发现插件/)).toBeTruthy());
  });

  it('加载失败只本块提示「读取失败请刷新」,其余区块照常', async () => {
    renderSection(backend({}, true));
    await waitFor(() => expect(screen.getByText('读取失败请刷新。')).toBeTruthy());
    expect(screen.getByLabelText('工作目录')).toBeTruthy();
  });

  it('「批准插件」→ set_plugin_approval approved:true,成功 toast 提示 MCP 待批准', async () => {
    renderSection(backend());
    await waitFor(() => expect(screen.getByRole('button', { name: '批准插件 example' })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '批准插件 example' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'set_plugin_approval', {
        name: 'example',
        approved: true,
      }),
    );
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('外接 MCP') && m.includes('已批准插件'))).toBe(true),
    );
  });

  it('已批准项显示「撤销批准」→ approved:false,toast 提示已移除', async () => {
    renderSection(backend({ plugin: { approved: true } }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '撤销批准 example' })).toBeTruthy(),
    );
    expect(screen.getByText(/^已批准 ·/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '撤销批准 example' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'set_plugin_approval', {
        name: 'example',
        approved: false,
      }),
    );
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('已撤销插件'))).toBe(true),
    );
  });

  it('批准失败弹 error toast(文案含失败原因,不带裸错误码)', async () => {
    callCapabilityMock.mockImplementation((_d: string, name: string) => {
      if (name === 'list_plugins') return Promise.resolve({ items: [PLUGIN] });
      return Promise.reject(new Error('仅限用户操作'));
    });
    render(<AgentSettingsSection />);
    await waitFor(() => expect(screen.getByRole('button', { name: '批准插件 example' })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '批准插件 example' }));
    await waitFor(() =>
      expect(toastTexts().some((m) => m.startsWith('批准失败：'))).toBe(true),
    );
  });
});
