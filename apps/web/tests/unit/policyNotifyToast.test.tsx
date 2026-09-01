/** L1 权限提示 toast 单测(phase-40 §9.9):agent.policy.notify 只弹 info toast,
 *  不进聊天时间线;空白 message 不弹;其余事件仍走 chatStore.dispatch。 */

import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { subscribeMock } = vi.hoisted(() => ({
  subscribeMock: vi.fn(() => () => {}),
}));

vi.mock('@/bridge/stream', () => ({ subscribe: subscribeMock }));

import { useChatStream } from '@/hooks/useChatStream';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';

/** 挂 hook 的探针组件(onNavigate 本阶段用不到) */
function HookProbe() {
  useChatStream(() => {});
  return null;
}

/** 捕获 useChatStream 注册进 subscribe 的事件回调 */
function handler() {
  return subscribeMock.mock.calls[0][1] as (ev: {
    seq: number;
    type: string;
    payload: Record<string, unknown>;
  }) => void;
}

beforeEach(() => {
  subscribeMock.mockClear();
  useChatStore.setState({ messages: [] });
  useUIStore.setState({ toasts: [] });
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ json: async () => ({ messages: [] }) } as Response),
  );
});

describe('agent.policy.notify → toast(phase-40)', () => {
  it('收到事件弹 info toast,消息不进时间线', () => {
    render(<HookProbe />);
    handler()({ seq: 1, type: 'agent.policy.notify', payload: { message: 'write_file: g.txt' } });
    const toasts = useUIStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0].type).toBe('info');
    expect(toasts[0].message).toBe('write_file: g.txt');
    expect(useChatStore.getState().messages).toHaveLength(0);
  });

  it('message 空白不弹 toast', () => {
    render(<HookProbe />);
    handler()({ seq: 2, type: 'agent.policy.notify', payload: { message: '   ' } });
    expect(useUIStore.getState().toasts).toHaveLength(0);
  });

  it('其余事件照旧 dispatch 进 chatStore(回归)', () => {
    render(<HookProbe />);
    handler()({ seq: 3, type: 'agent.observe', payload: { content: '观察句', acted: false } });
    expect(useUIStore.getState().toasts).toHaveLength(0);
    expect(useChatStore.getState().observe?.content).toBe('观察句');
  });
});
