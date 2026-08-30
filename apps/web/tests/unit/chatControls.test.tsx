/** 对话控制面单测(§9.7/§9.15/急停):仲裁读取与切换、急停闭环、徽章、AskUser 超时兜底。 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

// 保留真实 ServiceError(急停 NOT_FOUND 分支靠 instanceof + code 判定)
vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import { ServiceError } from '@/bridge/client';
import { ChatControls } from '@/widgets/chat/ChatControls';
import { AskDialog } from '@/widgets/chat/AskDialog';
import { useChatStore } from '@/stores/chatStore';

const RUNNING = {
  running: [
    { id: 'run-1', name: 'indexer', status: 'running', goal: '建索引', started_ts: 1 },
    { id: 'run-2', name: 'done-job', status: 'completed', goal: '已完成', started_ts: 2 },
  ],
};

function resetStore() {
  useChatStore.setState({
    messages: [],
    question: null,
    thinking: false,
    connected: true,
  });
}

beforeEach(() => {
  resetStore();
  callCapabilityMock.mockReset();
  callCapabilityMock.mockImplementation(async (_domain: string, name: string) => {
    if (name === 'get_setting') return { value: 'queue' };
    if (name === 'list_subagents') return { running: [] };
    return {};
  });
});

describe('ChatControls 仲裁模式', () => {
  it('读取设置并显示用户文案', async () => {
    callCapabilityMock.mockImplementation(async (_d: string, name: string) =>
      name === 'get_setting' ? { value: 'auto' } : { running: [] },
    );
    render(<ChatControls />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '仲裁模式' })).toHaveTextContent('仲裁:自动'),
    );
  });

  it('切换经 set_setting 后回读一致', async () => {
    // 有状态 mock:模拟后端 settings store,get_setting 回读 set 后的值
    let current = 'queue';
    callCapabilityMock.mockImplementation(async (_d: string, name: string, args: Record<string, unknown>) => {
      if (name === 'get_setting') return { value: current };
      if (name === 'set_setting') {
        current = String(args.value);
        return { key: args.key, ok: true };
      }
      return { running: [] };
    });
    render(<ChatControls />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '仲裁模式' })).toHaveTextContent('仲裁:排队'),
    );
    fireEvent.click(screen.getByRole('button', { name: '仲裁模式' }));
    fireEvent.click(screen.getByRole('option', { name: '仲裁:引导' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.arbiter.mode',
        value: 'guide',
      }),
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '仲裁模式' })).toHaveTextContent('仲裁:引导'),
    );
  });
});

describe('ChatControls 急停', () => {
  it('空闲时禁用;运行中可点,停 chat 并给出系统提示', async () => {
    const { rerender } = render(<ChatControls />);
    expect(screen.getByRole('button', { name: '急停' })).toBeDisabled();

    useChatStore.setState({ thinking: true });
    rerender(<ChatControls />);
    fireEvent.click(screen.getByRole('button', { name: '急停' }));

    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'cancel_run', {
        id_or_name: 'chat',
      }),
    );
    expect(useChatStore.getState().thinking).toBe(false);
    const last = useChatStore.getState().messages.at(-1);
    expect(last?.role).toBe('system');
    expect(last?.content).toContain('已中断当前对话任务');
  });

  it('目标不存在(NOT_FOUND)时也解除思考态,不卡输入', async () => {
    useChatStore.setState({ thinking: true });
    callCapabilityMock.mockImplementation(async (_d: string, name: string) => {
      if (name === 'cancel_run') {
        throw new ServiceError('AGENT.NOT_FOUND', '没有匹配的运行中实例: chat');
      }
      if (name === 'get_setting') return { value: 'queue' };
      return { running: [] };
    });
    render(<ChatControls />);
    fireEvent.click(screen.getByRole('button', { name: '急停' }));
    await waitFor(() => expect(useChatStore.getState().thinking).toBe(false));
    const last = useChatStore.getState().messages.at(-1);
    expect(last?.content).toContain('没有正在运行的实例');
  });
});

describe('运行中徽章', () => {
  it('只显示 status=running 的实例;点徽章停对应 id', async () => {
    callCapabilityMock.mockImplementation(async (_d: string, name: string) =>
      name === 'list_subagents' ? RUNNING : name === 'get_setting' ? { value: 'queue' } : {},
    );
    render(<ChatControls />);
    await waitFor(() => expect(screen.getByRole('button', { name: /indexer/ })).toBeTruthy());
    expect(screen.queryByRole('button', { name: /done-job/ })).toBeNull(); // completed 被过滤

    expect(screen.getByRole('button', { name: '急停' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: /indexer/ }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'cancel_run', {
        id_or_name: 'run-1',
      }),
    );
  });

  it('点徽章停非 chat 实例时不结束主对话思考态', async () => {
    useChatStore.setState({ thinking: true });
    callCapabilityMock.mockImplementation(async (_d: string, name: string) =>
      name === 'list_subagents' ? RUNNING : name === 'get_setting' ? { value: 'queue' } : {},
    );
    render(<ChatControls />);
    await waitFor(() => expect(screen.getByRole('button', { name: /indexer/ })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /indexer/ }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'cancel_run', {
        id_or_name: 'run-1',
      }),
    );
    expect(useChatStore.getState().thinking).toBe(true);
    const last = useChatStore.getState().messages.at(-1);
    expect(last?.content).toContain('已发送中断请求');
  });
});

describe('AskDialog 超时兜底', () => {
  it('回投命中 matched=false 时照常收起并提示,不无限卡住', async () => {
    callCapabilityMock.mockResolvedValue({ matched: false });
    useChatStore.setState({
      question: {
        questionId: 'q1',
        prompt: '选哪个?',
        kind: 'confirm',
        options: [],
        min: null,
        max: null,
      },
    });
    render(<AskDialog />);
    fireEvent.click(screen.getByRole('button', { name: '确认' }));

    await waitFor(() => expect(useChatStore.getState().question).toBeNull());
    const last = useChatStore.getState().messages.at(-1);
    expect(last?.role).toBe('system');
    expect(last?.content).toContain('已失效');
  });
});

describe('chatStore 超时兜底', () => {
  it('agent.message 到达时清掉未答问题(agent 已按默认继续)', () => {
    useChatStore.setState({
      question: {
        questionId: 'q2',
        prompt: '在吗?',
        kind: 'text',
        options: [],
        min: null,
        max: null,
      },
      thinking: true,
    });
    useChatStore.getState().dispatch({
      seq: 10,
      type: 'agent.message',
      payload: { content: '超时了,我先按默认做。' },
    });
    expect(useChatStore.getState().question).toBeNull();
    expect(useChatStore.getState().thinking).toBe(false);
  });
});
