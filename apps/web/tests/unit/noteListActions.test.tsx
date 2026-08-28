import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { vi } from 'vitest';
import type { Note } from '@/api/types';
import { NoteList } from '@/pages/notes/NoteList';

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

function Harness({
  variant,
  selecting = false,
  onSelect,
  onToggleSelect,
  onArchive,
  onExport,
  onDelete,
}: {
  variant: 'list' | 'card';
  selecting?: boolean;
  onSelect: (n: Note) => void;
  onToggleSelect: (id: string) => void;
  onArchive: (n: Note) => void;
  onExport: (n: Note) => void;
  onDelete: (n: Note) => void;
}) {
  const [menuId, setMenuId] = useState<string | null>(null);
  return (
    <NoteList
      notes={[sample()]}
      variant={variant}
      selectedIds={new Set()}
      menuId={menuId}
      selecting={selecting}
      onSelect={onSelect}
      onToggleSelect={onToggleSelect}
      onMenu={setMenuId}
      onArchive={onArchive}
      onExport={onExport}
      onDelete={onDelete}
      onPin={() => undefined}
    />
  );
}

describe('笔记清单条目操作', () => {
  it('未进入选择时不渲染复选框', () => {
    render(
      <Harness
        variant="card"
        onSelect={vi.fn()}
        onToggleSelect={vi.fn()}
        onArchive={vi.fn()}
        onExport={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.queryByRole('checkbox')).toBeNull();
  });

  it('选择模式下点条目只选中,不打开', () => {
    const onSelect = vi.fn();
    const onToggleSelect = vi.fn();
    render(
      <Harness
        variant="list"
        selecting
        onSelect={onSelect}
        onToggleSelect={onToggleSelect}
        onArchive={vi.fn()}
        onExport={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.queryByRole('checkbox')).toBeNull();
    fireEvent.click(screen.getByTestId('note-item'));
    expect(onToggleSelect).toHaveBeenCalledWith('n1');
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('选择模式下点卡片只勾选,不打开', () => {
    const onSelect = vi.fn();
    const onToggleSelect = vi.fn();
    render(
      <Harness
        variant="card"
        selecting
        onSelect={onSelect}
        onToggleSelect={onToggleSelect}
        onArchive={vi.fn()}
        onExport={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId('note-item'));
    expect(onToggleSelect).toHaveBeenCalledWith('n1');
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('列表菜单可归档与导出,不打开笔记', () => {
    const onSelect = vi.fn();
    const onArchive = vi.fn();
    const onExport = vi.fn();
    render(
      <Harness
        variant="list"
        onSelect={onSelect}
        onToggleSelect={vi.fn()}
        onArchive={onArchive}
        onExport={onExport}
        onDelete={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: '笔记操作' }));
    fireEvent.click(screen.getByRole('menuitem', { name: '归档' }));
    expect(onArchive).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '笔记操作' }));
    fireEvent.click(screen.getByRole('menuitem', { name: '导出 Markdown' }));
    expect(onExport).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('卡片菜单可移入回收站,不打开笔记', () => {
    const onSelect = vi.fn();
    const onDelete = vi.fn();
    render(
      <Harness
        variant="card"
        onSelect={onSelect}
        onToggleSelect={vi.fn()}
        onArchive={vi.fn()}
        onExport={vi.fn()}
        onDelete={onDelete}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: '笔记操作' }));
    fireEvent.click(screen.getByRole('menuitem', { name: '移入回收站' }));
    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();
  });
});
