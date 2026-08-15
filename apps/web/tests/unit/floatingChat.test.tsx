/** 悬浮窗:圆点未读计数、开面板清零、chat 同源消息流。 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { FloatingChat, useFloatingStore } from '@/widgets/FloatingChat';
import { useChatStore } from '@/pages/chat/chatStore';

const subscribeMock = vi.fn(() => () => {});

vi.mock('@/bridge/stream', () => ({ subscribe: (...args: unknown[]) => subscribeMock(...args) }));

// jsdom 无 scrollIntoView(MessageList 自动滚底依赖)
beforeAll(() => {
  Element.prototype.scrollIntoView = () => {};
});

beforeEach(() => {
  subscribeMock.mockClear().mockImplementation(() => () => {});
  useFloatingStore.setState({ open: false, unread: 0 });
  useChatStore.setState({
    messages: [], cards: {}, cardOrder: [], artifacts: [], question: null,
    connected: true, thinking: false,
  });
});

describe('FloatingChat 两态', () => {
  it('默认收起为圆点;agent.message 到达计未读;打开清零', async () => {
    let handler: ((ev: { type: string; payload: Record<string, unknown> }) => void) | null = null;
    subscribeMock.mockImplementation(
      (_patterns: string[], fn: typeof handler) => {
        handler = fn;
        return () => {};
      },
    );
    render(
      <MemoryRouter>
        <FloatingChat />
      </MemoryRouter>,
    );
    expect(screen.getByRole('button', { name: /打开对话/ })).toBeTruthy();
    expect(screen.queryByText('收起')).toBeNull();

    // 收起时收到两条 agent 消息 -> 未读 2
    handler?.({ type: 'agent.message', payload: { content: '你好' } });
    handler?.({ type: 'agent.message', payload: { content: '在吗' } });
    await waitFor(() => expect(useFloatingStore.getState().unread).toBe(2));
    expect(screen.getByText('2')).toBeTruthy();

    // 打开:未读清零,面板出现,消息流与 chat 同源
    fireEvent.click(screen.getByRole('button', { name: /打开对话/ }));
    expect(useFloatingStore.getState().open).toBe(true);
    expect(useFloatingStore.getState().unread).toBe(0);
    expect(screen.getByRole('button', { name: '收起' })).toBeTruthy();
    expect(screen.getByText('你好')).toBeTruthy();
    expect(screen.getByText('在吗')).toBeTruthy();
  });
});
