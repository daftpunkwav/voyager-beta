/** 设置页插件块单测(phase-72 整包 + phase-74 分项):挂载打 list_plugins、渲染
 *  名称/版本/批准状态/权限清单/明细、整包批准、自定义分项勾选、撤销;
 *  成功/失败 toast;不调 getApi()。 */

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

/** list_plugins 的样例:未批准、2 skill + 1 hook + 1 MCP(与 phase-72 区分开) */
const PLUGIN = {
  name: 'example',
  version: '0.1.0',
  description: '最小插件示例',
  approved: false,
  granularity: '',
  permissions: { scopes: ['notes.write'], network: 'off', fs: 'none' },
  contains: { skills: 2, hooks: 1, mcp: true },
  skills: [
    { name: 'daily-note', approved: false },
    { name: 'weekly-review', approved: false },
  ],
  hooks: [{ path: 'hooks/on-note-created.json', on: 'note.created', enabled: true, approved: false }],
  mcp: [{ id: 'example-search', approved: false, registered: false, tools_approved: [] }],
  path: 'example',
};

/** 结果回包:整包 loaded 3 skill? skills 是数组(装载的 skill 名) */
const RESULT = {
  name: 'example',
  approved: true,
  granularity: 'item',
  loaded: { skills: ['daily-note'], hooks: 1, mcp_registered: 1, mcp_skipped: false },
  skipped: { skills: [], hooks: [], mcp: [] },
};

function backend(
  overrides: Record<string, unknown> = {},
  failList = false,
  failApproval = false,
) {
  return (_domain: string, name: string, args: Record<string, unknown>) => {
    switch (name) {
      case 'list_plugins':
        if (failList) return Promise.reject(new Error('boom'));
        return Promise.resolve({
          items: overrides.items ?? [{ ...PLUGIN, ...(overrides.plugin as object) }],
        });
      case 'set_plugin_approval':
        if (failApproval) return Promise.reject(new Error('仅限用户操作'));
        return Promise.resolve({ ...RESULT, name: args.name, approved: args.approved });
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

let confirmMock: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  callCapabilityMock.mockReset();
  getApiMock.mockReset();
  useUIStore.setState({ toasts: [] });
  // 撤销批准走 window.confirm(phase-76):默认确认,个别用例改返回值
  confirmMock = vi.spyOn(window, 'confirm').mockReturnValue(true);
  confirmMock.mockClear(); // spy 复用同一 mock:清掉上一用例的 calls
});

describe('设置页插件块(phase-72)', () => {
  it('挂载打 list_plugins,渲染名称/版本/描述/未批准/权限清单与 contains;不调 getApi()', async () => {
    renderSection(backend());
    await waitFor(() => expect(screen.getByText('example v0.1.0')).toBeTruthy());
    expect(screen.getByText('最小插件示例')).toBeTruthy();
    expect(screen.getByText(/未批准 · 请求权限：notes\.write · 网络 off · 文件 none/)).toBeTruthy();
    expect(screen.getByText(/技能 2 · 钩子 1 · MCP 配置/)).toBeTruthy();
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

  it('「整包批准」→ set_plugin_approval granularity bundle,成功 toast 提示 MCP 待批准', async () => {
    renderSection(backend());
    await waitFor(() => expect(screen.getByRole('button', { name: '整包批准 example' })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '整包批准 example' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'set_plugin_approval', {
        name: 'example',
        approved: true,
        granularity: 'bundle',
      }),
    );
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('外接 MCP') && m.includes('已批准插件'))).toBe(true),
    );
  });

  it('已批准项显示「撤销批准」→ approved:false,toast 提示已移除', async () => {
    renderSection(
      backend({ plugin: { approved: true, granularity: 'bundle' } }),
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '撤销批准 example' })).toBeTruthy(),
    );
    expect(screen.getByText(/已批准（整包） · 请求权限/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '撤销批准 example' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'set_plugin_approval', {
        name: 'example',
        approved: false,
        granularity: 'bundle',
      }),
    );
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('已撤销插件'))).toBe(true),
    );
  });

  it('批准失败弹 error toast(文案含失败原因,不带裸错误码)', async () => {
    renderSection(backend({}, false, true));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '整包批准 example' })).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole('button', { name: '整包批准 example' }));
    await waitFor(() =>
      expect(toastTexts().some((m) => m.startsWith('批准失败：'))).toBe(true),
    );
  });
});

describe('设置页插件块自定义分项(phase-74)', () => {
  it('展开自定义批准展示 skill/hook/MCP 明细 checkbox,至少勾一项才可提交', async () => {
    renderSection(backend());
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '自定义批准 example' })).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole('button', { name: '自定义批准 example' }));
    // 明细 checkbox 渲染(accessibility label 由文本生成)
    expect(screen.getByRole('checkbox', { name: 'daily-note' })).toBeTruthy();
    expect(screen.getByRole('checkbox', { name: 'weekly-review' })).toBeTruthy();
    expect(screen.getByRole('checkbox', { name: 'note.created' })).toBeTruthy();
    expect(screen.getByRole('checkbox', { name: /example-search/ })).toBeTruthy();
    // 未勾选时提交禁用;勾选一项后可提交
    const submit = screen.getByRole('button', { name: '自定义批准' });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('checkbox', { name: 'daily-note' }));
    expect((submit as HTMLButtonElement).disabled).toBe(false);
  });

  it('勾选后提交 → granularity item + 勾选名单;成功 toast 与刷新', async () => {
    renderSection(backend());
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '自定义批准 example' })).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole('button', { name: '自定义批准 example' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'daily-note' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'note.created' }));
    fireEvent.click(screen.getByRole('button', { name: '自定义批准' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'set_plugin_approval', {
        name: 'example',
        approved: true,
        granularity: 'item',
        skills: ['daily-note'],
        hooks: ['hooks/on-note-created.json'],
        mcp: [],
      }),
    );
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('已批准插件') && m.includes('外接 MCP'))).toBe(true),
    );
  });

  it('已批准(分项)项可「修改分项」回填已勾选,再提交幂等重装', async () => {
    renderSection(
      backend({
        plugin: {
          approved: true,
          granularity: 'item',
          skills: [
            { name: 'daily-note', approved: true },
            { name: 'weekly-review', approved: false },
          ],
          hooks: [{ path: 'hooks/on-note-created.json', on: 'note.created', enabled: true, approved: true }],
        },
      }),
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '修改分项 example' })).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole('button', { name: '修改分项 example' }));
    // 已批准的分项预勾选
    expect((screen.getByRole('checkbox', { name: 'daily-note' }) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByRole('checkbox', { name: 'weekly-review' }) as HTMLInputElement).checked).toBe(false);
    // 取消勾选一个再提交 → 只装剩下勾选的
    fireEvent.click(screen.getByRole('checkbox', { name: 'daily-note' }));
    fireEvent.click(screen.getByRole('button', { name: '自定义批准' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'set_plugin_approval', {
        name: 'example',
        approved: true,
        granularity: 'item',
        skills: [],
        hooks: ['hooks/on-note-created.json'],
        mcp: [],
      }),
    );
  });

  it('分项批准失败弹 error toast 且不关闭勾选面板', async () => {
    renderSection(backend({}, false, true));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '自定义批准 example' })).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole('button', { name: '自定义批准 example' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'daily-note' }));
    fireEvent.click(screen.getByRole('button', { name: '自定义批准' }));
    await waitFor(() =>
      expect(toastTexts().some((m) => m.startsWith('批准失败：'))).toBe(true),
    );
  });
});

describe('设置页插件块撤销回收 MCP(phase-76)', () => {
  it('撤销弹 confirm,列出将回收的「已登记且未批准工具」MCP id 后再提交', async () => {
    renderSection(
      backend({
        plugin: {
          approved: true,
          granularity: 'bundle',
          mcp: [{ id: 'example-search', approved: true, registered: true, tools_approved: [] }],
        },
      }),
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '撤销批准 example' })).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole('button', { name: '撤销批准 example' }));
    expect(String(confirmMock.mock.calls[0]?.[0])).toContain('example-search');
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'set_plugin_approval', {
        name: 'example',
        approved: false,
        granularity: 'bundle',
      }),
    );
  });

  it('confirm 取消则不发撤销请求', async () => {
    confirmMock.mockReturnValue(false);
    renderSection(backend({ plugin: { approved: true, granularity: 'bundle' } }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '撤销批准 example' })).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole('button', { name: '撤销批准 example' }));
    await waitFor(() => expect(confirmMock).toHaveBeenCalled());
    expect(
      callCapabilityMock,
    ).not.toHaveBeenCalledWith(
      'agent',
      'set_plugin_approval',
      expect.objectContaining({ approved: false }),
    );
  });

  it('撤销回包披露回收结果:已回收列 id、未回收列原因', async () => {
    callCapabilityMock.mockImplementation(
      (_domain: string, name: string, args: Record<string, unknown>) => {
        if (name === 'list_plugins') {
          return Promise.resolve({ items: [{ ...PLUGIN, approved: true, granularity: 'bundle' }] });
        }
        if (name === 'set_plugin_approval') {
          return Promise.resolve({
            ...RESULT,
            name: args.name,
            approved: false,
            mcp_reclaimed: ['example-search'],
            mcp_reclaim_skipped: [{ id: 'manual-srv', reason: 'MCP 工具已批准，已保留' }],
          });
        }
        if (name === 'get_memory') return Promise.resolve(SNAPSHOT);
        return Promise.resolve({});
      },
    );
    render(<AgentSettingsSection />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '撤销批准 example' })).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole('button', { name: '撤销批准 example' }));
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('已同步移除其外接 MCP：example-search'))).toBe(
        true,
      ),
    );
    await waitFor(() =>
      expect(
        toastTexts().some((m) => m.includes('未回收：manual-srv（MCP 工具已批准，已保留）')),
      ).toBe(true),
    );
  });

  it('分项改勾回包带 mcp_reclaimed 时,批准 toast 一并披露被移除的 MCP', async () => {
    callCapabilityMock.mockImplementation(
      (_domain: string, name: string, args: Record<string, unknown>) => {
        if (name === 'list_plugins') {
          return Promise.resolve({ items: [{ ...PLUGIN }] });
        }
        if (name === 'set_plugin_approval') {
          return Promise.resolve({
            ...RESULT,
            name: args.name,
            approved: true,
            mcp_reclaimed: ['example-search'],
          });
        }
        if (name === 'get_memory') return Promise.resolve(SNAPSHOT);
        return Promise.resolve({});
      },
    );
    render(<AgentSettingsSection />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '自定义批准 example' })).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole('button', { name: '自定义批准 example' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'daily-note' }));
    fireEvent.click(screen.getByRole('button', { name: '自定义批准' }));
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('已移除取消勾选的 MCP：example-search'))).toBe(
        true,
      ),
    );
  });
});
