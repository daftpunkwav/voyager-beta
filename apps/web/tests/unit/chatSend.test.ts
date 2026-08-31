/** sendUserTurn:任意页把一句用户消息推进主时间线(phase-17)。 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { setOpen } = vi.hoisted(() => ({ setOpen: vi.fn() }));

vi.mock('@/widgets/FloatingChat', () => ({
  useFloatingStore: {
    getState: () => ({ setOpen }),
  },
}));

import { sendUserTurn } from '@/bridge/chatSend';
import { useChatStore } from '@/stores/chatStore';

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
});
