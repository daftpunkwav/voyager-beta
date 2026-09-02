/** sendUserTurn:任意页把一句用户消息推进主时间线(phase-17);
 *  phase-67 增补发送前配额守卫:满配额拒发不 POST、≥80% 提醒后照发。 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { setOpen, fetchQuotaGuardMock } = vi.hoisted(() => ({
  setOpen: vi.fn(),
  fetchQuotaGuardMock: vi.fn(),
}));

vi.mock('@/widgets/FloatingChat', () => ({
  useFloatingStore: {
    getState: () => ({ setOpen }),
  },
}));

vi.mock('@/bridge/quotaGuard', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/quotaGuard')>()),
  fetchQuotaGuard: fetchQuotaGuardMock,
}));

import { sendUserTurn } from '@/bridge/chatSend';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

describe('sendUserTurn', () => {
  beforeEach(() => {
    setOpen.mockReset();
    fetchQuotaGuardMock.mockReset();
    // 默认放行:未显式 stub 配额结果的用例不受守卫影响
    fetchQuotaGuardMock.mockResolvedValue({ action: 'allow' });
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
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ seq: 42 })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('POST 成功后写入 chatStore 并打开悬浮窗', async () => {
    await sendUserTurn('  【图谱向导】当前节点：abc。用户：为什么相连  ');
    expect(fetch).toHaveBeenCalledWith(
      '/api/chat/messages',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
      }),
    );
    const init = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({
      content: '【图谱向导】当前节点：abc。用户：为什么相连',
    });
    expect(useChatStore.getState().messages).toEqual([
      {
        seq: 42,
        role: 'user',
        content: '【图谱向导】当前节点：abc。用户：为什么相连',
      },
    ]);
    expect(setOpen).toHaveBeenCalledWith(true);
  });

  it('后端失败时不写入消息、不打开悬浮窗', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(null, 500));
    await expect(sendUserTurn('请分析这个仓库')).rejects.toThrow('发送失败(500)');
    expect(useChatStore.getState().messages).toEqual([]);
    expect(setOpen).not.toHaveBeenCalled();
  });

  it('满配额 block:抛错且不 POST、不写消息、不打开悬浮窗', async () => {
    fetchQuotaGuardMock.mockResolvedValue({
      action: 'block',
      reason: '今日 token 配额已用完，可在设置中调高或明日再试',
    });
    await expect(sendUserTurn('请分析这个仓库')).rejects.toThrow('今日 token 配额已用完');
    expect(fetch).not.toHaveBeenCalled();
    expect(useChatStore.getState().messages).toEqual([]);
    expect(setOpen).not.toHaveBeenCalled();
  });

  it('≥80% warn:提醒后照常发送', async () => {
    fetchQuotaGuardMock.mockResolvedValue({ action: 'warn', ratio: 0.8 });
    await sendUserTurn('继续分析');
    expect(fetch).toHaveBeenCalled();
    expect(useChatStore.getState().messages).toEqual([
      { seq: 42, role: 'user', content: '继续分析' },
    ]);
    expect(setOpen).toHaveBeenCalledWith(true);
    const toasts = useUIStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0].type).toBe('warning');
    expect(toasts[0].message).toContain('80%');
  });
});
