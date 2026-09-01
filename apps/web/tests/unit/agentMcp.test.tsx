/** 设置页外接 MCP 单测(phase-11b):挂载打 list_mcp_servers;添加/批准/移除
 *  打到对应能力;不调 getApi()。GlassSelect 不强测(默认 stdio + 整包即可覆盖提交)。 */

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

/** list_mcp_servers 的样例:未批准、已连上、逐项、有预览 */
const SERVER = {
  id: 'my-search',
  name: 'My Search',
  kind: 'stdio',
  command: 'npx',
  args: ['-y', 'x'],
  url: '',
  approval: 'item',
  approved: [],
  enabled: true,
  connected: true,
  error: '',
  preview: [
    { name: 'search', description: '搜索' },
    { name: 'fetch', description: '抓取' },
  ],
  mounted: [],
};

function backend(overrides: Record<string, unknown> = {}) {
  return (_domain: string, name: string, args: Record<string, unknown>) => {
    switch (name) {
      case 'list_mcp_servers':
        return Promise.resolve(overrides.list_mcp_servers ?? [{ ...SERVER, ...overrides.server }]);
      case 'add_mcp_server':
        return Promise.resolve({ ok: true, id: args.id, connected: true, error: '', preview: [] });
      case 'approve_mcp_tools':
        return Promise.resolve({ ok: true, approved: args.names, mounted: ['mcp__my-search__search'] });
      case 'remove_mcp_server':
        return Promise.resolve({ ok: true });
      case 'preview_mcp_tools':
        return Promise.resolve({ id: args.id, preview: SERVER.preview });
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

describe('设置页外接 MCP(phase-11b)', () => {
  it('挂载打 list_mcp_servers,渲染名称/未批准/预览工具;不调 getApi()', async () => {
    renderSection(backend());
    await waitFor(() => expect(screen.getByText('My Search')).toBeTruthy());
    expect(screen.getByText(/未批准/)).toBeTruthy();
    // 预览清单经逐项 checkbox 的唯一 aria-label 断言(描述文案易与网络权限块撞词)
    expect(screen.getByLabelText('my-search · search')).toBeTruthy();
    expect(screen.getByLabelText('my-search · fetch')).toBeTruthy();
    expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'list_mcp_servers', {});
    expect(getApiMock).not.toHaveBeenCalled();
  });

  it('空列表显示添加指引', async () => {
    renderSection(backend({ list_mcp_servers: [] }));
    await waitFor(() =>
      expect(screen.getByText(/还没有外接 MCP/)).toBeTruthy(),
    );
  });

  it('连接失败显示本条 error,不整页挂', async () => {
    renderSection(backend({ server: { connected: false, error: '连接被拒(测试)' } }));
    await waitFor(() => expect(screen.getByText(/连接被拒/)).toBeTruthy());
    // 其他区块照常:轮数输入仍可查
    expect(screen.getByLabelText('ReAct 轮数上限')).toBeTruthy();
  });

  it('填 id 提交 → add_mcp_server 带上表单字段;成功 toast 提示名册时机', async () => {
    renderSection(backend({ list_mcp_servers: [] }));
    await waitFor(() => expect(screen.getByLabelText('MCP id')).toBeTruthy());
    fireEvent.change(screen.getByLabelText('MCP id'), { target: { value: 'my-search' } });
    fireEvent.change(screen.getByLabelText('MCP command'), { target: { value: 'npx' } });
    fireEvent.change(screen.getByLabelText('MCP args'), { target: { value: '-y\nx' } });
    fireEvent.click(screen.getByRole('button', { name: '添加 MCP' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'add_mcp_server', {
        id: 'my-search',
        name: 'my-search',
        kind: 'stdio',
        command: 'npx',
        args: ['-y', 'x'],
        url: '',
        approval: 'package',
      }),
    );
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('下一句或新对话可见'))).toBe(true),
    );
  });

  it('逐项:勾选工具后「批准所选」→ approve 带勾选名;批准 toast 写明下一句可见', async () => {
    renderSection(backend());
    await waitFor(() => expect(screen.getByLabelText('my-search · search')).toBeTruthy());
    fireEvent.click(screen.getByLabelText('my-search · search'));
    fireEvent.click(screen.getByRole('button', { name: '批准所选 My Search' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'approve_mcp_tools', {
        id: 'my-search',
        names: ['search'],
      }),
    );
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('下一句或新对话可见'))).toBe(true),
    );
  });

  it('整包:「批准全部」→ approve names=["*"]', async () => {
    renderSection(backend({ server: { approval: 'package' } }));
    await waitFor(() => expect(screen.getByRole('button', { name: '批准全部 My Search' })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '批准全部 My Search' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'approve_mcp_tools', {
        id: 'my-search',
        names: ['*'],
      }),
    );
  });

  it('「刷新工具列表」→ preview_mcp_tools', async () => {
    renderSection(backend());
    await waitFor(() => expect(screen.getByRole('button', { name: '刷新工具列表 My Search' })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '刷新工具列表 My Search' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'preview_mcp_tools', {
        id: 'my-search',
      }),
    );
  });

  it('「移除」走确认框,确认后打 remove_mcp_server', async () => {
    renderSection(backend());
    await waitFor(() => expect(screen.getByRole('button', { name: '移除 My Search' })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '移除 My Search' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(/确定移除/)).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('button', { name: '移除' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'remove_mcp_server', {
        id: 'my-search',
      }),
    );
  });
});
