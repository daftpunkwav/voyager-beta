/** 活动页:EventRow 摘要模板、未知类型兜底、撤销按钮范围、store 合并去重。 */

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { EventRow, summarize } from '@/pages/activity/EventRow';
import {
  append, COMPENSATIONS, useActivityStore, type FeedEvent,
} from '@/pages/activity/activityStore';

const callMock = vi.fn();

vi.mock('@/bridge/client', () => ({
  callCapability: (...args: unknown[]) => callMock(...args),
  ServiceError: class extends Error {
    code = '';
    hint = '';
  },
}));

function ev(p: Partial<FeedEvent> = {}): FeedEvent {
  return {
    seq: 1,
    id: 'e1',
    type: 'note.created',
    actor: { kind: 'user', id: 'local' },
    payload: { note_id: 'n1', title: 'ReAct 要点' },
    ts: 1723680000,
    trace_id: '',
    ...p,
  };
}

beforeEach(() => {
  useActivityStore.setState({ events: [], cursor: 0, group: 'all', loading: false, error: null, caps: new Set() });
});

describe('summarize 摘要模板', () => {
  it('已识别类型按模板渲染', () => {
    expect(summarize(ev()).text).toBe('用户 创建笔记《ReAct 要点》');
    expect(summarize(ev({ type: 'settings.changed', payload: { key: 'agent.style' } })).text)
      .toBe('用户 修改设置 agent.style');
    const failed = summarize(ev({ type: 'task.failed', payload: { error: '引擎闪退' } }));
    expect(failed.text).toContain('任务失败:引擎闪退');
    expect(failed.tone).toBe('error');
    const agent = summarize(ev({ type: 'agent.message', actor: { kind: 'agent', id: 'lucien' }, payload: { content: '你好' } }));
    expect(agent.text).toBe('lucien 回复:你好');
    expect(summarize(ev({ type: 'note.created', actor: { kind: 'agent', id: 'miyai' } })).text)
      .toContain('miyai');
  });

  it('未知类型兜底显示原文,不崩', () => {
    const out = summarize(ev({ type: 'future.event.kind', payload: { x: 1 } }));
    expect(out.text).toBe('future.event.kind');
    expect(out.tone).toBe('muted');
  });
});

describe('EventRow 撤销按钮范围', () => {
  it('note.created 有撤销,两段确认后回调', () => {
    const onUndo = vi.fn();
    render(<EventRow event={ev()} canUndo onUndo={onUndo} />);
    fireEvent.click(screen.getByRole('button', { name: '撤销' }));
    expect(onUndo).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '确认撤销' }));
    expect(onUndo).toHaveBeenCalledTimes(1);
  });

  it('canUndo=false 或补偿表外类型无按钮;note.edited 置灰提示', () => {
    const { rerender } = render(<EventRow event={ev()} canUndo={false} onUndo={() => {}} />);
    expect(screen.queryByRole('button', { name: '撤销' })).toBeNull();

    rerender(<EventRow event={ev({ type: 'task.completed', payload: {} })} canUndo onUndo={() => {}} />);
    expect(screen.queryByRole('button', { name: '撤销' })).toBeNull();

    rerender(<EventRow event={ev({ type: 'note.edited', payload: { note_id: 'n1' } })} canUndo onUndo={() => {}} />);
    expect(screen.queryByRole('button', { name: '撤销' })).toBeNull();
    expect(screen.getByText('暂不支持')).toBeTruthy();
  });

  it('点击行展开 payload 详情', () => {
    render(<EventRow event={ev()} canUndo={false} onUndo={() => {}} />);
    fireEvent.click(screen.getByTitle(/展开/));
    expect(screen.getByText(/"title": "ReAct 要点"/)).toBeTruthy();
  });
});

describe('store 合并与补偿', () => {
  it('append 按 seq 去重并升序;超过 MAX_ROWS 截断', () => {
    const e1 = ev({ seq: 1 });
    const e2 = ev({ seq: 2, type: 'note.edited' });
    const first = append([], [e1, e2]);
    const again = append(first.events, [e1, e2]); // 轮询重复
    expect(again.events).toHaveLength(2);
    expect(again.cursor).toBe(2);
    expect(again.events.map((e) => e.seq)).toEqual([1, 2]);
  });

  it('undo 调补偿能力(note.created -> delete_note)并立即追平', async () => {
    callMock.mockResolvedValue({});
    const refresh = vi.fn().mockResolvedValue(undefined);
    useActivityStore.setState({ refresh: refresh as never });
    await useActivityStore.getState().undo(ev());
    expect(callMock).toHaveBeenCalledWith('notes', 'delete_note', { note_id: 'n1' });
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('补偿表只含 note.created / source.added', () => {
    expect(Object.keys(COMPENSATIONS)).toEqual(['note.created', 'source.added']);
  });
});
