/** Phase-09 单测:主动消息出处(§9.8/§10.2)。
 *  主动气泡要带「为什么找我」触发源行;普通 agent 回复没有;
 *  历史回放(applyHistory)里的主动消息同样带出处。 */

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';

import { MessageList } from '@/widgets/chat/MessageList';
import { useChatStore, type ChatEvent } from '@/stores/chatStore';
import { summarize, type FeedEvent } from '@/bridge/feed';

let seq = 0;
function dispatch(type: string, payload: Record<string, unknown>) {
  seq += 1;
  useChatStore.getState().dispatch({ seq, type, payload } as ChatEvent);
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
  seq = 0;
  useChatStore.setState({
    messages: [],
    cards: {},
    cardOrder: [],
    artifacts: [],
    question: null,
    thinking: false,
    connected: true,
    currentStep: null,
  });
});

describe('主动消息出处行', () => {
  it('dispatch 主动消息(proactive+reason)显示「为什么找我」', () => {
    dispatch('agent.message', {
      content: '欢迎回来,接着看 langgraph 吗?',
      proactive: true,
      kind: 'greeting',
      reason: '你打开了应用',
    });
    render(
      <MemoryRouter>
        <MessageList />
      </MemoryRouter>,
    );
    expect(screen.getByText(/欢迎回来/)).toBeInTheDocument();
    expect(screen.getByText('主动')).toBeInTheDocument();
    expect(screen.getByLabelText('为什么找我:你打开了应用')).toHaveTextContent(
      '为什么找我:你打开了应用',
    );
  });

  it('普通 agent 回复没有出处行和主动药丸', () => {
    dispatch('agent.message', { content: '笔记写好了' });
    render(
      <MemoryRouter>
        <MessageList />
      </MemoryRouter>,
    );
    expect(screen.getByText('笔记写好了')).toBeInTheDocument();
    expect(screen.queryByText('主动')).toBeNull();
    expect(screen.queryByText(/为什么找我/)).toBeNull();
  });

  it('主动但后端没给 reason 时只有药丸,不渲染空出处行', () => {
    dispatch('agent.message', { content: '旧格式主动消息', proactive: true });
    render(
      <MemoryRouter>
        <MessageList />
      </MemoryRouter>,
    );
    expect(screen.getByText('主动')).toBeInTheDocument();
    expect(screen.queryByText(/为什么找我/)).toBeNull();
  });

  it('历史回放(applyHistory)里的主动消息仍带出处', () => {
    const events = [
      { seq: 1, type: 'user.message', payload: { content: '嗨' }, ts: 1 },
      {
        seq: 2,
        type: 'agent.message',
        payload: { content: '在忙别的事吗?', proactive: true, kind: 'followup', reason: '你一段时间没回复' },
        ts: 2,
      },
    ] as unknown as ChatEvent[];
    useChatStore.getState().applyHistory(events);
    render(
      <MemoryRouter>
        <MessageList />
      </MemoryRouter>,
    );
    expect(screen.getByLabelText('为什么找我:你一段时间没回复')).toBeInTheDocument();
  });
});

describe('活动 feed 的主动出处', () => {
  const ev = (payload: Record<string, unknown>): FeedEvent =>
    ({
      seq: 1,
      id: 'e1',
      type: 'agent.message',
      actor: { kind: 'agent', id: 'lucien' },
      payload,
      ts: 1,
      trace_id: '',
    }) as FeedEvent;

  it('proactive 消息摘要带触发源出处', () => {
    const row = summarize(ev({ content: '欢迎回来', proactive: true, kind: 'greeting', reason: '你打开了应用' }));
    expect(row.text).toContain('主动(你打开了应用)');
    expect(row.text).toContain('欢迎回来');
  });

  it('普通回复保持「回复:」文案,不带出处', () => {
    const row = summarize(ev({ content: '笔记写好了' }));
    expect(row.text).toContain('回复:');
    expect(row.text).not.toContain('主动');
  });
});
