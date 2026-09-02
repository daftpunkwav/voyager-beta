/** Phase-68 C 单测:EmbedAgentChat 发送顺序。
 *  配额 block(sendUserTurn 拒绝)时:输入保留、不插「已发到主对话」假阳性
 *  系统行、仅 error toast;发送成功后才清空输入并落 user + 系统两行。 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { sendUserTurnMock } = vi.hoisted(() => ({
  sendUserTurnMock: vi.fn(),
}));

vi.mock('@/bridge/chatSend', () => ({
  sendUserTurn: sendUserTurnMock,
}));

vi.mock('@/hooks/useLlmAvailable', () => ({
  useLlmAvailable: () => 'ok',
}));

import { EmbedAgentChat } from '@/components/agent/EmbedAgentChat';
import { useUIStore } from '@/stores/uiStore';

beforeAll(() => {
  // jsdom 缺口:组件滚动 effect 用到 matchMedia / scrollIntoView
  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
  }
  Element.prototype.scrollIntoView = () => {};
});

beforeEach(() => {
  sendUserTurnMock.mockReset();
  useUIStore.setState({ toasts: [] });
});

function typeAndSend(text: string) {
  fireEvent.change(screen.getByLabelText('导入助手 对话输入'), { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: '发送' }));
}

describe('EmbedAgentChat 发送顺序(phase-68 C)', () => {
  it('配额 block:输入保留、无假阳性系统行、仅 error toast', async () => {
    sendUserTurnMock.mockRejectedValue(new Error('今日 token 配额已用完'));
    const { container } = render(<EmbedAgentChat mode="import" title="导入助手" />);

    typeAndSend('推荐几个类似的项目');
    await waitFor(() => expect(useUIStore.getState().toasts).toHaveLength(1));
    const toast = useUIStore.getState().toasts[0];
    expect(toast.type).toBe('error');
    expect(toast.message).toBe('今日 token 配额已用完');

    expect(sendUserTurnMock).toHaveBeenCalledTimes(1);
    expect(sendUserTurnMock).toHaveBeenCalledWith(expect.stringContaining('推荐几个类似的项目'));
    // 输入不丢:textarea 仍是用户原文
    expect((screen.getByLabelText('导入助手 对话输入') as HTMLTextAreaElement).value)
      .toBe('推荐几个类似的项目');
    // 无乐观行:不插 user 气泡,更无「已发到主对话」系统行
    // (textarea 的 textContent 恰为输入文本,故用气泡 class 而非 queryByText 判行)
    expect(container.querySelector('.embed-msg--user')).toBeNull();
    expect(screen.queryByText('已发到主对话，请打开悬浮窗查看。')).not.toBeInTheDocument();
  });

  it('发送成功:清空输入,落 user 行 + 「已发到主对话」系统行', async () => {
    sendUserTurnMock.mockResolvedValue(undefined);
    render(<EmbedAgentChat mode="import" title="导入助手" />);

    typeAndSend('我 star 的项目都是什么类型');
    await waitFor(() =>
      expect(screen.getByText('已发到主对话，请打开悬浮窗查看。')).toBeInTheDocument(),
    );
    expect(screen.getByText('我 star 的项目都是什么类型')).toBeInTheDocument();
    expect(
      (screen.getByLabelText('导入助手 对话输入') as HTMLTextAreaElement).value,
    ).toBe('');
  });
});
