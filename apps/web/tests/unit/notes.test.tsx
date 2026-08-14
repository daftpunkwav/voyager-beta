/** 笔记页:store 摘要/全文分离契约、自动保存触发与 flush、删除二次确认。 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NoteEditor } from '@/pages/notes/NoteEditor';
import { NoteMeta } from '@/pages/notes/NoteMeta';
import { type Note, type NoteSummary, useNotesStore } from '@/pages/notes/notesStore';

const callMock = vi.fn();

vi.mock('@/bridge/client', () => ({
  callCapability: (...args: unknown[]) => callMock(...args),
  ServiceError: class extends Error {
    code = '';
    hint = '';
  },
}));

function summary(p: Partial<NoteSummary> = {}): NoteSummary {
  return {
    id: 'n1',
    title: '标题',
    tags: [],
    source_id: '',
    node_id: '',
    created_ts: 1,
    updated_ts: 2,
    excerpt: '摘要…',
    ...p,
  };
}

function note(p: Partial<Note> = {}): Note {
  return { ...summary(), content: '正文', ...p };
}

beforeEach(() => {
  callMock.mockReset();
  useNotesStore.setState({
    summaries: [],
    current: null,
    cache: {},
    filterTag: '',
    sort: 'updated',
    pageSize: 100,
    autosaveS: 5,
    loading: false,
    error: null,
  });
});

describe('notesStore', () => {
  it('init:设置键 + 摘要列表(不期待 content 字段)', async () => {
    callMock.mockImplementation((_d, name) => {
      if (name === 'get_setting') return Promise.resolve({ value: 3 });
      if (name === 'list_notes') return Promise.resolve([summary({ id: 'a' }), summary({ id: 'b' })]);
      return Promise.resolve({});
    });
    await useNotesStore.getState().init();
    const s = useNotesStore.getState();
    expect(s.autosaveS).toBe(3);
    expect(s.summaries).toHaveLength(2);
    expect('content' in s.summaries[0]).toBe(false); // 摘要无 content 是契约
  });

  it('open:命中缓存不再请求;save 后缓存与摘要同步', async () => {
    callMock.mockImplementation((_d, name) => {
      if (name === 'get_note') return Promise.resolve(note({ id: 'n1' }));
      if (name === 'update_note') return Promise.resolve(note({ id: 'n1', title: '新标题', updated_ts: 9 }));
      return Promise.resolve({});
    });
    await useNotesStore.getState().open('n1');
    await useNotesStore.getState().open('n1'); // 第二次走缓存
    expect(callMock).toHaveBeenCalledTimes(1);

    useNotesStore.setState({ summaries: [summary({ id: 'n1', title: '标题' })] });
    const saved = await useNotesStore.getState().save('n1', { title: '新标题' });
    expect(saved.title).toBe('新标题');
    expect(useNotesStore.getState().summaries[0].title).toBe('新标题');
    expect(useNotesStore.getState().cache.n1.title).toBe('新标题');
  });

  it('remove:清列表/缓存/当前选中', async () => {
    callMock.mockResolvedValue({ deleted: 'n1' });
    useNotesStore.setState({
      summaries: [summary({ id: 'n1' })],
      cache: { n1: note({ id: 'n1' }) },
      current: note({ id: 'n1' }),
    });
    await useNotesStore.getState().remove('n1');
    const s = useNotesStore.getState();
    expect(s.summaries).toHaveLength(0);
    expect(s.cache.n1).toBeUndefined();
    expect(s.current).toBeNull();
  });
});

describe('NoteEditor 自动保存', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('输入置脏,到点触发 update_note;未改动不触发', async () => {
    callMock.mockResolvedValue(note({ id: 'n1' }));
    useNotesStore.setState({ current: note({ id: 'n1' }), autosaveS: 5 });

    const { container } = render(<NoteEditor />);
    const textarea = container.querySelector('textarea') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: '新内容' } });

    await vi.advanceTimersByTimeAsync(4900);
    expect(callMock).not.toHaveBeenCalledWith('notes', 'update_note', expect.anything());
    await vi.advanceTimersByTimeAsync(200); // 满 5s,触发并等待保存链
    expect(callMock).toHaveBeenCalledWith('notes', 'update_note', {
      note_id: 'n1',
      title: '标题',
      content: '新内容',
    });
  });

  it('autosave_s=0 时不自动保存,失焦 flush', async () => {
    callMock.mockResolvedValue(note({ id: 'n1' }));
    useNotesStore.setState({ current: note({ id: 'n1' }), autosaveS: 0 });
    const { container } = render(<NoteEditor />);
    const textarea = container.querySelector('textarea') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: '手动保存内容' } });
    await vi.advanceTimersByTimeAsync(60_000);
    expect(callMock).not.toHaveBeenCalled(); // 定时器关闭
    fireEvent.blur(textarea);
    await vi.advanceTimersByTimeAsync(0); // flush 微任务,保存链完成
    expect(callMock).toHaveBeenCalledWith('notes', 'update_note', {
      note_id: 'n1',
      title: '标题',
      content: '手动保存内容',
    });
  });
});

describe('NoteMeta 删除二次确认', () => {
  it('先确认才调 delete_note', async () => {
    callMock.mockResolvedValue({ deleted: 'n1' });
    useNotesStore.setState({ current: note({ id: 'n1' }) });
    render(<NoteMeta />);
    fireEvent.click(screen.getByText('删除笔记'));
    expect(callMock).not.toHaveBeenCalled(); // 未确认不删
    fireEvent.click(screen.getByText('确认删除'));
    await waitFor(() =>
      expect(callMock).toHaveBeenCalledWith('notes', 'delete_note', { note_id: 'n1' }),
    );
  });
});
