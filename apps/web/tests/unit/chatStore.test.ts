/** chatStore 事件分发:agent.ask、task.* 、agent.message 与历史重建。 */

import { beforeEach, describe, expect, it } from 'vitest';
import { type ChatEvent, useChatStore } from '@/pages/chat/chatStore';

function ev(type: string, payload: Record<string, unknown>, seq = 1): ChatEvent {
  return { seq, type, payload };
}

beforeEach(() => {
  useChatStore.setState({
    messages: [],
    cards: {},
    cardOrder: [],
    question: null,
    connected: false,
    thinking: false,
  });
});

describe('chatStore.dispatch', () => {
  it('agent.message 追加气泡并解除思考态;proactive 透传', () => {
    useChatStore.setState({ thinking: true });
    useChatStore.getState().dispatch(ev('agent.message', { content: '你好' }, 5));
    useChatStore.getState().dispatch(
      ev('agent.message', { content: '在忙吗', proactive: true }, 6),
    );
    const msgs = useChatStore.getState().messages;
    expect(msgs).toHaveLength(2);
    expect(msgs[0]).toMatchObject({ role: 'agent', content: '你好', proactive: false });
    expect(msgs[1].proactive).toBe(true);
    expect(useChatStore.getState().thinking).toBe(false);
  });

  it('agent.ask 建立 PendingQuestion', () => {
    useChatStore.getState().dispatch(
      ev('agent.ask', {
        question_id: 'q1',
        prompt: '选一个',
        kind: 'choice',
        options: ['A', 'B'],
        min: null,
        max: null,
      }),
    );
    expect(useChatStore.getState().question).toEqual({
      questionId: 'q1',
      prompt: '选一个',
      kind: 'choice',
      options: ['A', 'B'],
      min: null,
      max: null,
    });
  });

  it('task.progress→completed 按 source_id 聚合进度卡', () => {
    const s = useChatStore.getState();
    s.dispatch(ev('task.progress', { source_id: 's1', project: 'repo', progress: 0.4, stage: 'clone' }, 2));
    s.dispatch(ev('task.completed', { source_id: 's1', progress: 1.0 }, 3));
    const card = useChatStore.getState().cards.s1;
    expect(card.status).toBe('completed');
    expect(card.progress).toBe(1);
    expect(card.label).toBe('repo');
    expect(useChatStore.getState().cardOrder).toEqual(['s1']);
  });

  it('task.failed 记录错误且不覆盖已有卡', () => {
    const s = useChatStore.getState();
    s.dispatch(ev('task.progress', { job_id: 'j1', project: '索引', progress: 0.2, stage: 'run' }));
    s.dispatch(ev('task.failed', { job_id: 'j1', error: 'boom' }));
    const card = useChatStore.getState().cards.j1;
    expect(card.status).toBe('failed');
    expect(card.error).toBe('boom');
  });

  it('agent.navigate 插系统提示气泡', () => {
    useChatStore.getState().dispatch(ev('agent.navigate', { path: '/settings' }));
    const m = useChatStore.getState().messages[0];
    expect(m.role).toBe('system');
    expect(m.content).toContain('/settings');
  });

  it('note.created 追加产物卡(note_id 与标题)', () => {
    useChatStore
      .getState()
      .dispatch(ev('note.created', { note_id: 'n7', title: 'ReAct 要点' }, 9));
    expect(useChatStore.getState().artifacts).toEqual([
      { seq: 9, noteId: 'n7', title: 'ReAct 要点' },
    ]);
    // 无 note_id 的坏事件不入卡
    useChatStore.getState().dispatch(ev('note.created', { title: '孤儿' }, 10));
    expect(useChatStore.getState().artifacts).toHaveLength(1);
  });

  it('历史重建:user/agent 双向且不触发思考态', () => {
    useChatStore.getState().applyHistory([
      { seq: 1, type: 'user.message', payload: { content: '在吗' } },
      { seq: 2, type: 'agent.message', payload: { content: '在' } },
    ]);
    const msgs = useChatStore.getState().messages;
    expect(msgs.map((m) => m.role)).toEqual(['user', 'agent']);
    expect(useChatStore.getState().thinking).toBe(false);
  });

  it('appendLocal 置思考态(发送后等待 agent 回复)', () => {
    useChatStore.getState().appendLocal({ seq: 9, role: 'user', content: 'hi' });
    expect(useChatStore.getState().thinking).toBe(true);
  });
});
