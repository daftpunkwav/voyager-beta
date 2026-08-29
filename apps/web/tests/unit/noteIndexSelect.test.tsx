import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Note } from '@/api/types';
import { NoteIndex } from '@/pages/notes/NoteIndex';

function sample(partial: Partial<Note> = {}): Note {
  return {
    id: 'n1',
    title: '标题甲',
    content: '摘要正文',
    source_id: '',
    tags: [],
    created_ts: 1_700_000_000,
    updated_ts: 1_700_000_000,
    pinned: false,
    archived: false,
    ...partial,
  };
}

function renderIndex(notes: Note[] = [sample(), sample({ id: 'n2', title: '标题乙' })]) {
  return render(
    <NoteIndex
      notes={notes}
      layout="list"
      listState="active"
      onLayoutChange={vi.fn()}
      onListStateChange={vi.fn()}
      query=""
      onQuery={vi.fn()}
      sort="updated"
      onSort={vi.fn()}
      filter="all"
      onFilter={vi.fn()}
      sourceId=""
      onSourceId={vi.fn()}
      density="comfortable"
      onDensity={vi.fn()}
      projectOptions={[]}
      projectNames={new Map()}
      onOpen={vi.fn()}
      onNew={vi.fn()}
      onTrash={vi.fn()}
      onAssist={vi.fn()}
      onPin={vi.fn()}
      onArchive={vi.fn()}
      onExport={vi.fn()}
      onDelete={vi.fn()}
      empty={notes.length === 0}
    />,
  );
}

describe('笔记首页批量选择', () => {
  it('首页范围用「当前」,不用「在用」', () => {
    renderIndex();
    expect(screen.getByTestId('notes-list-state-active')).toHaveTextContent('当前');
    expect(screen.queryByText('在用')).toBeNull();
  });

  it('点批量后不出现勾选框,尚未点选时没有选择信息', () => {
    renderIndex();
    expect(screen.queryByRole('checkbox')).toBeNull();
    fireEvent.click(screen.getByTestId('notes-select-btn'));
    expect(screen.queryByRole('checkbox')).toBeNull();
    expect(screen.queryByTestId('notes-bulk-bar')).toBeNull();
    expect(screen.getByTestId('notes-select-btn')).toHaveAccessibleName('完成');
    expect(screen.getByTestId('notes-bulk-select-all')).toHaveAccessibleName('全选');
  });

  it('点任意一篇立刻出现已选信息与操作', () => {
    renderIndex();
    fireEvent.click(screen.getByTestId('notes-select-btn'));
    fireEvent.click(screen.getAllByTestId('note-item')[0]);
    expect(screen.getAllByTestId('note-item')[0]).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('notes-bulk-bar')).toHaveTextContent('已选 1 篇');
    expect(screen.getByTestId('notes-bulk-archive')).toBeTruthy();
    expect(screen.getByTestId('notes-bulk-export')).toBeTruthy();
    expect(screen.getByTestId('notes-bulk-delete')).toBeTruthy();
  });

  it('取消选择后选择信息先退出再卸掉,仍留在批量模式', () => {
    vi.useFakeTimers();
    try {
      renderIndex();
      fireEvent.click(screen.getByTestId('notes-select-btn'));
      fireEvent.click(screen.getAllByTestId('note-item')[0]);
      fireEvent.click(screen.getByTestId('notes-bulk-clear'));
      expect(screen.getByTestId('notes-bulk-bar').className).toMatch(/is-exit/);
      act(() => {
        vi.advanceTimersByTime(420);
      });
      expect(screen.queryByTestId('notes-bulk-bar')).toBeNull();
      expect(screen.queryByRole('checkbox')).toBeNull();
      expect(screen.getByTestId('notes-select-btn')).toHaveAccessibleName('完成');
    } finally {
      vi.useRealTimers();
    }
  });
});
