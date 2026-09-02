/** useChatSend 配额守卫单测(phase-67):
 *  满配额拒发(postChatMessage 不调、draft 保留、error toast)、
 *  ≥80% warning toast 且同一会话只提醒一次、不限照常发送。 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { fetchQuotaGuardMock, postChatMessageMock } = vi.hoisted(() => ({
  fetchQuotaGuardMock: vi.fn(),
  postChatMessageMock: vi.fn(),
}));

vi.mock('@/bridge/chatSend', () => ({
  postChatMessage: postChatMessageMock,
}));

vi.mock('@/bridge/quotaGuard', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/quotaGuard')>()),
  fetchQuotaGuard: fetchQuotaGuardMock,
}));

vi.mock('@/hooks/useLlmAvailable', () => ({
  useLlmAvailable: () => 'ok',
}));

import { useChatSend } from '@/hooks/useChatSend';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';

function resetStores() {
  useUIStore.setState({ toasts: [] });
  useChatStore.setState({
    messages: [],
    cards: {},
    cardOrder: [],
    artifacts: [],
    question: null,
    thinking: false,
    connected: true,
    currentStep: null,
    observe: null,
  });
}

beforeEach(() => {
  resetStores();
  fetchQuotaGuardMock.mockReset();
  postChatMessageMock.mockReset();
});

describe('useChatSend 配额守卫(phase-67)', () => {
  it('满配额 block:不调 postChatMessage、draft 保留、error toast', async () => {
    fetchQuotaGuardMock.mockResolvedValue({ action: 'block', reason: '今日 token 配额已用完' });
    const { result } = renderHook(() => useChatSend());

    act(() => result.current.setDraft('  帮我查一下  '));
    await act(async () => {
      await result.current.send();
    });

    expect(postChatMessageMock).not.toHaveBeenCalled();
    expect(result.current.draft).toBe('  帮我查一下  ');
    expect(result.current.sending).toBe(false);
    const toasts = useUIStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0].type).toBe('error');
    expect(toasts[0].message).toBe('今日 token 配额已用完');
    expect(useChatStore.getState().messages).toEqual([]);
  });

  it('≥80% warn:照常发送 + warning toast;同会话第二次发送不再提醒', async () => {
    fetchQuotaGuardMock.mockResolvedValue({ action: 'warn', ratio: 0.85 });
    postChatMessageMock.mockResolvedValue(42);
    const { result } = renderHook(() => useChatSend());

    act(() => result.current.setDraft('第一条'));
    await act(async () => {
      await result.current.send();
    });

    expect(postChatMessageMock).toHaveBeenCalledWith('第一条');
    expect(result.current.draft).toBe('');
    let toasts = useUIStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0].type).toBe('warning');
    expect(toasts[0].message).toContain('85%');
    expect(useChatStore.getState().messages[0]).toEqual({ seq: 42, role: 'user', content: '第一条' });

    act(() => result.current.setDraft('第二条'));
    await act(async () => {
      await result.current.send();
    });

    expect(postChatMessageMock).toHaveBeenCalledTimes(2);
    toasts = useUIStore.getState().toasts;
    expect(toasts.filter((t) => t.type === 'warning')).toHaveLength(1);
  });

  it('不限(allow)照常发送,无 toast', async () => {
    fetchQuotaGuardMock.mockResolvedValue({ action: 'allow' });
    postChatMessageMock.mockResolvedValue(7);
    const { result } = renderHook(() => useChatSend());

    act(() => result.current.setDraft('随便聊聊'));
    await act(async () => {
      await result.current.send();
    });

    expect(postChatMessageMock).toHaveBeenCalledWith('随便聊聊');
    expect(useUIStore.getState().toasts).toEqual([]);
    expect(useChatStore.getState().messages[0]?.seq).toBe(7);
  });

  it('发送失败仍还原草稿并追加系统气泡(原有行为不回归)', async () => {
    fetchQuotaGuardMock.mockResolvedValue({ action: 'allow' });
    postChatMessageMock.mockRejectedValue(new Error('后端不可达'));
    const { result } = renderHook(() => useChatSend());

    act(() => result.current.setDraft('会失败的一句'));
    await act(async () => {
      await result.current.send();
    });

    await waitFor(() => expect(result.current.draft).toBe('会失败的一句'));
    const messages = useChatStore.getState().messages;
    expect(messages.at(-1)?.role).toBe('system');
    expect(useChatStore.getState().thinking).toBe(false);
  });

  it('守卫查询期间 send 重入被 sending 短路(不重复查询、不双发)', async () => {
    let release!: (v: { action: 'allow' }) => void;
    fetchQuotaGuardMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    );
    postChatMessageMock.mockResolvedValue(1);
    const { result } = renderHook(() => useChatSend());

    act(() => result.current.setDraft('只发一条'));
    let first!: Promise<void>;
    act(() => {
      first = result.current.send();
    });
    // 守卫挂起期间 sending 已置位:重入立即被入口短路
    expect(result.current.sending).toBe(true);
    await act(async () => {
      await result.current.send();
    });
    expect(fetchQuotaGuardMock).toHaveBeenCalledTimes(1);

    release({ action: 'allow' });
    await act(async () => {
      await first;
    });
    expect(postChatMessageMock).toHaveBeenCalledTimes(1);
    expect(result.current.sending).toBe(false);
    expect(useChatStore.getState().messages).toEqual([
      { seq: 1, role: 'user', content: '只发一条' },
    ]);
  });
});
