/** 设置页 Agent 只读附加目录单测(phase-54):
 *  挂载草稿按行展示;保存 trim/去空行后打到 agent.fs.read_roots 的 JSON 数组;
 *  相对路径 / 含 .. 段 / 空白输入只警告,不发请求。 */

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
  'agent.fs.read_roots': ['D:\\docs', '/home/me/papers'],
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

beforeEach(() => {
  SETTINGS['agent.fs.read_roots'] = ['D:\\docs', '/home/me/papers'];
  callCapabilityMock.mockReset();
  callCapabilityMock.mockImplementation(backend);
  getApiMock.mockReset();
  useUIStore.setState({ toasts: [] });
});

/** 等 get_setting 草稿填进 textarea(挂载是异步的) */
async function waitDraft(expected: string) {
  await waitFor(() =>
    expect((screen.getByLabelText('只读附加目录') as HTMLTextAreaElement).value).toBe(expected),
  );
}

describe('只读附加目录(phase-54)', () => {
  it('挂载时读取草稿:数组按行展示', async () => {
    render(<AgentSettingsSection />);
    await waitDraft('D:\\docs\n/home/me/papers');
  });

  it('编辑保存 trim/去空行后打到 agent.fs.read_roots 的 JSON 数组', async () => {
    render(<AgentSettingsSection />);
    await waitDraft('D:\\docs\n/home/me/papers');

    const box = screen.getByLabelText('只读附加目录') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: ' /tmp/a\nD:\\b \n\n' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.fs.read_roots',
        value: ['/tmp/a', 'D:\\b'],
      }),
    );
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'success')).toBe(true),
    );
  });

  it('相对路径拒收:警告 toast,不发请求', async () => {
    render(<AgentSettingsSection />);
    await waitDraft('D:\\docs\n/home/me/papers');

    const box = screen.getByLabelText('只读附加目录') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'docs\n/tmp/a' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true),
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.fs.read_roots' }),
    );
  });

  it('含 .. 段拒收:警告 toast,不发请求', async () => {
    render(<AgentSettingsSection />);
    await waitDraft('D:\\docs\n/home/me/papers');

    const box = screen.getByLabelText('只读附加目录') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'D:\\a\\..\\b' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true),
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.fs.read_roots' }),
    );
  });

  it('空行-only 保存为空数组', async () => {
    render(<AgentSettingsSection />);
    await waitDraft('D:\\docs\n/home/me/papers');

    const box = screen.getByLabelText('只读附加目录') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: '\n\n' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.fs.read_roots',
        value: [],
      }),
    );
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'success')).toBe(true),
    );
  });
});
