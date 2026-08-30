/** Phase-05 单测:任务卡完整态(completed/failed 无前序也建卡、label 优先级、跳转链接)
 *  与笔记产物就地预览(展开取全文 / 失败说明 / 收起)。 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, beforeAll, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import { ServiceError } from '@/bridge/client';
import { MessageList, StepLine, TaskCards } from '@/widgets/chat/MessageList';
import { useChatStore, type ChatEvent, type ProgressCard } from '@/stores/chatStore';

let seq = 0;
function dispatch(type: string, payload: Record<string, unknown>) {
  seq += 1;
  useChatStore.getState().dispatch({ seq, type, payload } as ChatEvent);
}

function card(partial: Partial<ProgressCard> & { key: string }): ProgressCard {
  return { label: partial.key, progress: 0, stage: '', status: 'running', ...partial };
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
  callCapabilityMock.mockReset();
  callCapabilityMock.mockResolvedValue({});
});

describe('chatStore 任务卡完整态', () => {
  it('只推 task.completed(无先前 progress)也建完成卡', () => {
    dispatch('task.completed', { job_id: 'j-1', project: 'voyager', progress: 1.0 });
    const { cards, cardOrder } = useChatStore.getState();
    expect(cardOrder).toContain('j-1');
    expect(cards['j-1']).toMatchObject({
      label: 'voyager',
      status: 'completed',
      progress: 1,
    });
  });

  it('只推 task.failed(无先前 progress)也建失败卡,error 可见', () => {
    dispatch('task.failed', { job_id: 'j-2', project: 'voyager', error: '队列爆炸' });
    expect(useChatStore.getState().cards['j-2']).toMatchObject({
      status: 'failed',
      error: '队列爆炸',
    });
  });

  it('sources 风格 payload(无 project)卡文案用 kind,不用裸 uuid', () => {
    dispatch('task.failed', { source_id: 'abc-123', kind: 'doc', error: '解析失败: 损坏的 PDF' });
    expect(useChatStore.getState().cards['abc-123']).toMatchObject({
      label: 'doc',
      error: '解析失败: 损坏的 PDF',
      link: '/sources/doc/abc-123',
    });
  });

  it('repo 风格 payload 无 kind 时,source_id 仍落到 repo 详情页', () => {
    dispatch('task.failed', { source_id: 'r-1', error: 'clone 超时' });
    expect(useChatStore.getState().cards['r-1']?.link).toBe('/sources/repo/r-1');
  });

  it('graph 的 job_id 没有详情页,不造链接', () => {
    dispatch('task.progress', { job_id: 'g-1', project: 'demo', stage: 'start' });
    expect(useChatStore.getState().cards['g-1']?.link).toBeUndefined();
  });

  it('progress 先行后 completed:保留 label,进度置满,stage 不沿用旧的 running 值', () => {
    dispatch('task.progress', { job_id: 'g-2', project: 'demo', stage: 'start', progress: 0.2 });
    dispatch('task.completed', { job_id: 'g-2', project: 'demo', progress: 1.0 });
    expect(useChatStore.getState().cards['g-2']).toMatchObject({
      label: 'demo',
      stage: '已完成',
      status: 'completed',
      progress: 1,
    });
  });

  it('enqueued 缺 stage 时给中文兜底,不再显示技术词', () => {
    dispatch('task.enqueued', { job_id: 'g-3', project: 'demo' });
    expect(useChatStore.getState().cards['g-3']?.stage).toBe('进行中');
  });

  it('note.created 追加产物,空 note_id 过滤', () => {
    dispatch('note.created', { note_id: 'n-1', title: '会议纪要' });
    dispatch('note.created', { note_id: '', title: '占位' });
    expect(useChatStore.getState().artifacts.map((a) => a.noteId)).toEqual(['n-1']);
  });
});

describe('chatStore 工具步骤可见(phase-06)', () => {
  it('agent.step 设置当前步骤,新步骤覆盖旧的', () => {
    dispatch('agent.step', { subagent: 'chat', name: 'activate_tools', kind: 'tool', summary: '' });
    expect(useChatStore.getState().currentStep).toMatchObject({
      name: 'activate_tools',
      subagent: 'chat',
    });
    dispatch('agent.step', { subagent: 'chat', name: 'notes__create_note', kind: 'tool' });
    expect(useChatStore.getState().currentStep?.name).toBe('notes__create_note');
  });

  it('agent.message(回合有产出)清掉当前步骤', () => {
    dispatch('agent.step', { subagent: 'chat', name: 'notes__create_note' });
    dispatch('agent.message', { content: '笔记写好了' });
    expect(useChatStore.getState().currentStep).toBeNull();
  });

  it('StepLine 渲染「正在:{name}」,空步骤不渲染', () => {
    const { rerender } = render(<StepLine />);
    expect(screen.queryByRole('status')).toBeNull();

    dispatch('agent.step', { subagent: 'Miyai', name: 'notes__mark_note_span' });
    rerender(<StepLine />);
    expect(screen.getByRole('status')).toHaveTextContent('Miyai · 正在:notes__mark_note_span');
  });
});

describe('TaskCards 渲染', () => {
  it('失败卡展示 error 文案;带 link 的卡整卡可点进资源页', () => {
    useChatStore.setState({
      cards: {
        'abc-123': card({
          key: 'abc-123',
          label: 'doc',
          stage: 'parse',
          status: 'failed',
          error: '解析失败: 损坏的 PDF',
          link: '/sources/doc/abc-123',
        }),
      },
      cardOrder: ['abc-123'],
    });
    render(
      <MemoryRouter>
        <TaskCards />
      </MemoryRouter>,
    );
    expect(screen.getByText(/解析失败: 损坏的 PDF/)).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute('href', '/sources/doc/abc-123');
  });
});

describe('笔记产物就地预览', () => {
  it('点击展开经 notes.get_note 取全文并渲染 Markdown,再点收起', async () => {
    callCapabilityMock.mockResolvedValue({
      title: '会议纪要',
      content: '# 标题行\n\n正文段落',
    });
    useChatStore.setState({ artifacts: [{ seq: 1, noteId: 'n-1', title: '会议纪要' }] });
    render(
      <MemoryRouter>
        <MessageList />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: /会议纪要/ }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('notes', 'get_note', { note_id: 'n-1' }),
    );
    expect(await screen.findByRole('heading', { name: '标题行' })).toBeInTheDocument();
    // 跳笔记页入口保留
    expect(screen.getByRole('link', { name: '笔记页 →' })).toHaveAttribute(
      'href',
      '/notes?note=n-1',
    );
    // 收起
    fireEvent.click(screen.getByRole('button', { name: /会议纪要/ }));
    expect(screen.queryByRole('heading', { name: '标题行' })).not.toBeInTheDocument();
  });

  it('收起再展开不重复请求全文(已加载缓存)', async () => {
    callCapabilityMock.mockResolvedValue({ title: 't', content: '正文' });
    useChatStore.setState({ artifacts: [{ seq: 1, noteId: 'n-2', title: 't' }] });
    render(
      <MemoryRouter>
        <MessageList />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: /已创建笔记/ }));
    await screen.findByText('正文');
    fireEvent.click(screen.getByRole('button', { name: /已创建笔记/ }));
    fireEvent.click(screen.getByRole('button', { name: /已创建笔记/ }));
    await screen.findByText('正文');
    expect(callCapabilityMock).toHaveBeenCalledTimes(1);
  });

  it('笔记已删除(NOT_FOUND)给可见说明,不空白', async () => {
    callCapabilityMock.mockRejectedValue(
      new ServiceError('notes.NOT_FOUND', '笔记不存在: n-9'),
    );
    useChatStore.setState({ artifacts: [{ seq: 1, noteId: 'n-9', title: '被删的笔记' }] });
    render(
      <MemoryRouter>
        <MessageList />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: /被删的笔记/ }));
    expect(await screen.findByText(/笔记不存在或已被删除/)).toBeInTheDocument();
  });
});
