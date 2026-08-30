/** 无可用 LLM key 空态单测(phase-12 §9.18):确认无可用提供商时 Chat 页/悬浮窗
 *  显示空态且禁发送(按钮 + Enter);list_providers 查询失败不锁死对话。 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock, subscribeMock } = vi.hoisted(() => ({
  callCapabilityMock: vi.fn(),
  subscribeMock: vi.fn(() => () => {}),
}));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

vi.mock('@/bridge/stream', () => ({ subscribe: subscribeMock }));

import { ChatPage } from '@/pages/chat/ChatPage';
import { FloatingChat } from '@/widgets/FloatingChat';
import { useChatStore } from '@/stores/chatStore';

/** list_providers 的返回(用例间改写);PROVIDERS_FAIL=true 模拟查询失败 */
let PROVIDERS: Array<Record<string, unknown>> = [];
let PROVIDERS_FAIL = false;

function backend(_domain: string, name: string) {
  switch (name) {
    case 'list_providers':
      return PROVIDERS_FAIL
        ? Promise.reject(new Error('network down'))
        : Promise.resolve(PROVIDERS);
    case 'get_setting':
      return Promise.resolve({ value: 'queue' });
    case 'list_subagents':
      return Promise.resolve({ running: [] });
    default:
      return Promise.resolve({});
  }
}

beforeAll(() => {
  // jsdom 缺口:MessageList 的滚动 effect 用到 matchMedia / scrollIntoView
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
  PROVIDERS = [];
  PROVIDERS_FAIL = false;
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
  callCapabilityMock.mockReset();
  callCapabilityMock.mockImplementation(backend);
});

/** 往 Chat 页输入框打字(placeholder 随空态变化,先等它稳定) */
async function typeIntoChatPage(text: string) {
  const box = screen.getByPlaceholderText(/说点什么|先在设置里配置 LLM/);
  fireEvent.change(box, { target: { value: text } });
  return screen.getByRole('button', { name: '发送' });
}

describe('ChatPage 无 key 空态', () => {
  it('无可用提供商:显示空态、placeholder 变化、输入后发送仍禁用', async () => {
    PROVIDERS = [{ id: 'p1', enabled: true, has_api_key: false }];
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/还没有可用的 LLM 提供商/)).toBeTruthy();
    expect(screen.getByRole('link', { name: '设置 → LLM' })).toBeTruthy();

    const send = await typeIntoChatPage('你好');
    expect(send).toBeDisabled(); // 有草稿也禁发(Enter 同走 send() 早退)
    expect(
      screen.getByPlaceholderText('先在设置里配置 LLM'),
    ).toBeTruthy();
  });

  it('有可用提供商:不显示空态,输入后可发送', async () => {
    PROVIDERS = [{ id: 'p1', enabled: true, has_api_key: true }];
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('llm', 'list_providers'),
    );
    const send = await typeIntoChatPage('你好');
    await waitFor(() => expect(send).not.toBeDisabled());
    expect(screen.queryByText(/还没有可用的 LLM 提供商/)).toBeNull();
  });

  it('list_providers 失败:不误判为无 key,发送不锁死', async () => {
    PROVIDERS_FAIL = true;
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('llm', 'list_providers'),
    );
    const send = await typeIntoChatPage('你好');
    await waitFor(() => expect(send).not.toBeDisabled());
    expect(screen.queryByText(/还没有可用的 LLM 提供商/)).toBeNull();
  });
});

describe('FloatingChat 无 key 空态', () => {
  it('展开面板后显示空态且发送禁用', async () => {
    PROVIDERS = [{ id: 'p1', enabled: false, has_api_key: true }]; // disabled ≠ 可用
    render(
      <MemoryRouter>
        <FloatingChat />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: /打开对话/ }));
    expect(await screen.findByText(/还没有可用的 LLM 提供商/)).toBeTruthy();
    const box = screen.getByPlaceholderText('先在设置里配置 LLM');
    fireEvent.change(box, { target: { value: '你好' } });
    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled();
  });
});
