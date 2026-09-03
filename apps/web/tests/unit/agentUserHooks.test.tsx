/** 设置页用户钩子块单测(phase-78):挂载打 list_user_hooks 渲染文件名/on/停用与
 *  未装载态、空态指引、「重新加载」调 reload_user_hooks、成功 toast 含装载数量、
 *  skipped 披露、失败 toast、busy 防双提交;不调 getApi()。 */

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
  'agent.workspace.dir': 'workspace',
};

const HOOKS = [
  { path: 'note-watch.json', on: 'note.created', enabled: true, description: '笔记新建', loaded: true },
  { path: 'offline.json', on: 'note.deleted', enabled: false, description: '已停用示例', loaded: false },
];

function backend(
  overrides: { items?: unknown[]; failList?: boolean; failReload?: boolean; reload?: object } = {},
) {
  return (_domain: string, name: string, _args: Record<string, unknown>) => {
    switch (name) {
      case 'list_user_hooks':
        if (overrides.failList) return Promise.reject(new Error('boom'));
        return Promise.resolve({ items: overrides.items ?? HOOKS });
      case 'reload_user_hooks':
        if (overrides.failReload) return Promise.reject(new Error('仅限用户操作'));
        return Promise.resolve({ loaded: 2, event_patterns: ['note.created'], ...overrides.reload });
      case 'get_memory':
        return Promise.resolve(SNAPSHOT);
      case 'get_setting':
        return Promise.resolve({ value: SETTINGS[String(_args.key)] });
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

describe('设置页用户钩子块(phase-78)', () => {
  it('挂载打 list_user_hooks,渲染文件名/on/停用与未装载态;不调 getApi()', async () => {
    renderSection(backend());
    await waitFor(() => expect(screen.getByText('note-watch.json')).toBeTruthy());
    expect(screen.getByText('offline.json')).toBeTruthy();
    expect(screen.getByText('note.created')).toBeTruthy();
    expect(screen.getByText(/note\.deleted · 已停用 · 未装载/)).toBeTruthy();
    expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'list_user_hooks', {});
    expect(getApiMock).not.toHaveBeenCalled();
  });

  it('空清单显示放置指引(说明目录与改文件后点重载)', async () => {
    renderSection(backend({ items: [] }));
    await waitFor(() => expect(screen.getByText(/hooks\/ 下/)).toBeTruthy());
  });

  it('加载失败只本块提示「读取失败请刷新」,其余区块照常', async () => {
    renderSection(backend({ failList: true }));
    await waitFor(() => expect(screen.getByText('读取失败请刷新。')).toBeTruthy());
    expect(screen.getByLabelText('工作目录')).toBeTruthy();
  });

  it('「重新加载」调 reload_user_hooks,成功 toast 含装载数量并刷新清单', async () => {
    renderSection(backend());
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '重新加载用户钩子' })).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole('button', { name: '重新加载用户钩子' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'reload_user_hooks', {}),
    );
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('已重新加载用户钩子') && m.includes('装载 2 个'))).toBe(
        true,
      ),
    );
    // reload 成功后又打了一次 list_user_hooks 刷新清单
    const listCalls = callCapabilityMock.mock.calls.filter((c) => c[1] === 'list_user_hooks');
    expect(listCalls.length).toBeGreaterThanOrEqual(2);
  });

  it('回包带 skipped 时在 toast 披露跳过的文件与原因', async () => {
    renderSection(
      backend({
        reload: { skipped: [{ path: 'broken.json', reason: '无法解析: 坏 JSON' }] },
      }),
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '重新加载用户钩子' })).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole('button', { name: '重新加载用户钩子' }));
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('broken.json') && m.includes('坏 JSON'))).toBe(true),
    );
  });

  it('重载失败弹 error toast(文案含后端可读消息)', async () => {
    renderSection(backend({ failReload: true }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '重新加载用户钩子' })).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole('button', { name: '重新加载用户钩子' }));
    await waitFor(() =>
      expect(toastTexts().some((m) => m.startsWith('重载失败：') && m.includes('仅限用户操作'))).toBe(
        true,
      ),
    );
  });

  it('busy 防双提交:请求未返回时按钮禁用,双击只发一次', async () => {
    let resolveReload!: (v: unknown) => void;
    callCapabilityMock.mockImplementation(
      (_domain: string, name: string, _args: Record<string, unknown>) => {
        if (name === 'list_user_hooks') return Promise.resolve({ items: HOOKS });
        if (name === 'reload_user_hooks') {
          return new Promise((resolve) => {
            resolveReload = resolve;
          });
        }
        if (name === 'get_memory') return Promise.resolve(SNAPSHOT);
        return Promise.resolve({});
      },
    );
    render(<AgentSettingsSection />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '重新加载用户钩子' })).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole('button', { name: '重新加载用户钩子' }));
    await waitFor(() =>
      expect(
        (screen.getByRole('button', { name: '重新加载用户钩子' }) as HTMLButtonElement).disabled,
      ).toBe(true),
    );
    fireEvent.click(screen.getByRole('button', { name: '重新加载用户钩子' })); // 禁用态不再发
    const reloadCalls = callCapabilityMock.mock.calls.filter((c) => c[1] === 'reload_user_hooks');
    expect(reloadCalls).toHaveLength(1);
    resolveReload({ loaded: 2, event_patterns: [] });
    await waitFor(() =>
      expect(
        (screen.getByRole('button', { name: '重新加载用户钩子' }) as HTMLButtonElement).disabled,
      ).toBe(false),
    );
  });
});
