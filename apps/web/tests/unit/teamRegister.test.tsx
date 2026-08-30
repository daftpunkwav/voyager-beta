/** TeamPage 造人 + 急停单测(phase-07):提交参数形态(不裁剪不传 allowed_tools /
 *  白名单传数组)、非法 name 前端拦截、同名覆盖确认、cancel_run 急停与 chat 思考态。 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

// 保留真实 ServiceError(急停 NOT_FOUND 分支靠 instanceof + code 判定)
vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import { TeamPage } from '@/pages/team/TeamPage';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';

/** 有状态 mock:模拟后端 registry / spawner,register 与 cancel 都改内存态 */
let definitions: Array<Record<string, unknown>> = [];
let running: Array<Record<string, unknown>> = [];

function backend(_domain: string, name: string, args: Record<string, unknown>) {
  switch (name) {
    case 'list_personas':
      return Promise.resolve([
        {
          key: 'orchestrator',
          display_name: 'Lucien',
          style: '',
          default_mode: 'react',
          tool_allow: null,
          system_prompt: '',
        },
      ]);
    case 'list_tools':
      return Promise.resolve([
        { name: 'read_file', description: '读文件' },
        { name: 'write_file', description: '写文件' },
      ]);
    case 'list_subagents':
      return Promise.resolve({ definitions, running });
    case 'register_subagent': {
      definitions = [
        ...definitions.filter((d) => d.name !== args.name),
        {
          name: args.name,
          mode: args.mode ?? 'react',
          description: args.description,
          persona: args.persona ?? '',
          allowed_tools: (args.allowed_tools as string[] | undefined) ?? null,
          max_rounds: (args.max_rounds as number | undefined) ?? null,
          max_tool_calls: (args.max_tool_calls as number | undefined) ?? null,
          network_mode: (args.network_mode as string | undefined) ?? '',
        },
      ];
      return Promise.resolve({ name: args.name, mode: args.mode ?? 'react', allowed_tools: args.allowed_tools ?? null });
    }
    case 'cancel_run':
      running = running.filter((r) => r.id !== args.id_or_name && r.name !== args.id_or_name);
      return Promise.resolve({ cancelled: [args.id_or_name] });
    default:
      return Promise.resolve({});
  }
}

beforeEach(() => {
  definitions = [];
  running = [{ id: 'run-1', name: 'indexer', status: 'running', goal: '建索引', started_ts: 1 }];
  callCapabilityMock.mockReset();
  callCapabilityMock.mockImplementation(backend);
  window.localStorage.clear();
  useUIStore.setState({ toasts: [] });
  useChatStore.setState({ messages: [], question: null, thinking: false, connected: true });
});

/** 渲染并等初载完成(人格区出现即 loading 已结束) */
async function renderPage() {
  render(<TeamPage />);
  await waitFor(() => expect(screen.getByRole('heading', { name: '人格' })).toBeTruthy());
}

function fillForm(name: string, description: string) {
  fireEvent.change(screen.getByLabelText('名称'), { target: { value: name } });
  fireEvent.change(screen.getByLabelText('描述'), { target: { value: description } });
}

describe('造人表单(phase-07)', () => {
  it('不裁剪提交时不带 allowed_tools,注册后定义出现在列表', async () => {
    await renderPage();
    fillForm('scout', '只读侦察员');
    fireEvent.click(screen.getByRole('button', { name: '注册' }));

    // 参数形态:恰好四个字段,没有 allowed_tools 键
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'register_subagent', {
        name: 'scout',
        description: '只读侦察员',
        mode: 'react',
        persona: '',
      }),
    );
    // 成功后刷新 definitions,页面出现该定义
    await waitFor(() => expect(screen.getByText('只读侦察员')).toBeTruthy());
    expect(useUIStore.getState().toasts.some((t) => t.type === 'success')).toBe(true);
  });

  it('指定白名单:0 项禁止提交;勾选后提交工具数组', async () => {
    await renderPage();
    fillForm('scout', '侦察');
    fireEvent.click(screen.getByRole('radio', { name: '指定白名单' }));

    fireEvent.click(screen.getByRole('button', { name: '注册' }));
    expect(screen.getByText('指定白名单时至少勾选 1 项工具')).toBeTruthy();
    expect(callCapabilityMock).not.toHaveBeenCalledWith('agent', 'register_subagent', expect.anything());

    fireEvent.click(screen.getByRole('checkbox', { name: 'read_file' }));
    fireEvent.click(screen.getByRole('button', { name: '注册' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'register_subagent', {
        name: 'scout',
        description: '侦察',
        mode: 'react',
        persona: '',
        allowed_tools: ['read_file'],
      }),
    );
  });

  it('非法 name 前端拦截,不发注册请求', async () => {
    await renderPage();
    fillForm('Bad Name', '非法名');
    fireEvent.click(screen.getByRole('button', { name: '注册' }));

    expect(screen.getByText(/名称须为小写/)).toBeTruthy();
    expect(callCapabilityMock).not.toHaveBeenCalledWith('agent', 'register_subagent', expect.anything());
  });

  it('带轮数+网络注册(phase-10):请求体带三个新键,卡片显示档位', async () => {
    await renderPage();
    fillForm('guard', '守门员');
    fireEvent.change(screen.getByLabelText('ReAct 轮数'), { target: { value: '12' } });
    fireEvent.change(screen.getByLabelText('工具轮数'), { target: { value: '30' } });
    fireEvent.click(screen.getByRole('button', { name: '网络权限档位' }));
    fireEvent.click(screen.getByRole('option', { name: '白名单' }));
    fireEvent.click(screen.getByRole('button', { name: '注册' }));

    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'register_subagent', {
        name: 'guard',
        description: '守门员',
        mode: 'react',
        persona: '',
        max_rounds: 12,
        max_tool_calls: 30,
        network_mode: 'whitelist',
      }),
    );
    // 注册后刷新 definitions,卡片显示轮数与网络档位
    await waitFor(() => expect(screen.getByText('守门员')).toBeTruthy());
    expect(screen.getByText(/轮数:\s*12 \/ 30/)).toBeTruthy();
    expect(screen.getByText('网络:白名单')).toBeTruthy();
  });

  it('轮数填非正整数前端拦截,不发注册请求', async () => {
    await renderPage();
    fillForm('bad_rounds', '非法轮数');
    fireEvent.change(screen.getByLabelText('ReAct 轮数'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: '注册' }));

    expect(screen.getByText(/ReAct 轮数须为正整数/)).toBeTruthy();
    expect(callCapabilityMock).not.toHaveBeenCalledWith('agent', 'register_subagent', expect.anything());
  });

  it('同名已存在时先弹覆盖确认,确认后才提交', async () => {
    definitions = [
      { name: 'scout', mode: 'react', description: '旧定义', persona: '', allowed_tools: null },
    ];
    await renderPage();
    fillForm('scout', '新定义');
    fireEvent.click(screen.getByRole('button', { name: '注册' }));

    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(callCapabilityMock).not.toHaveBeenCalledWith('agent', 'register_subagent', expect.anything());

    fireEvent.click(screen.getByRole('button', { name: '覆盖' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith(
        'agent',
        'register_subagent',
        expect.objectContaining({ name: 'scout' }),
      ),
    );
  });
});

describe('实例急停(phase-07)', () => {
  it('运行中实例点急停调 cancel_run(id) 并立刻从列表拿掉', async () => {
    await renderPage();
    expect(screen.getByText('indexer')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '急停' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'cancel_run', { id_or_name: 'run-1' }),
    );
    await waitFor(() => expect(screen.queryByText('indexer')).toBeNull());
    expect(useUIStore.getState().toasts.some((t) => t.type === 'success')).toBe(true);
  });

  it('急停 chat 主实例时清对话思考态,用 toast 反馈,不往对话流塞消息', async () => {
    useChatStore.setState({ thinking: true });
    running = [{ id: 'chat', name: 'chat', status: 'running', goal: '与用户对话', started_ts: 1 }];
    await renderPage();

    fireEvent.click(screen.getByRole('button', { name: '急停' }));
    await waitFor(() => expect(useChatStore.getState().thinking).toBe(false));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'cancel_run', { id_or_name: 'chat' }),
    );
    expect(useChatStore.getState().messages).toHaveLength(0);
    expect(
      useUIStore.getState().toasts.some((t) => t.message.includes('对话主实例')),
    ).toBe(true);
  });
});
