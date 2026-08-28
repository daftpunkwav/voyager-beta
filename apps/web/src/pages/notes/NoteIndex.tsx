/** 笔记首页:只列清单(列表 / 卡片),不打开编辑器。 */

import { useMemo, useState } from 'react';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { GlassSelect } from '@/components/common/GlassSelect';
import type { Note } from '@/api/types';
import { sortNotes, type NotesLayout, type NotesListState, type NotesSort } from './noteUtils';
import { NoteList } from './NoteList';

interface NoteIndexProps {
  notes: Note[];
  layout: NotesLayout;
  listState: NotesListState;
  onLayoutChange: (layout: NotesLayout) => void;
  onListStateChange: (state: NotesListState) => void;
  searchQuery: string;
  onSearch: (q: string) => void;
  projectFilter: string;
  onProjectFilter: (id: string) => void;
  projectOptions: { value: string; label: string }[];
  projectNames: Map<string, string>;
  onOpen: (note: Note) => void;
  onNew: () => void;
  onTrash: () => void;
  onPin: (note: Note, pinned: boolean) => void;
  empty: boolean;
}

export function NoteIndex({
  notes,
  layout,
  listState,
  onLayoutChange,
  onListStateChange,
  searchQuery,
  onSearch,
  projectFilter,
  onProjectFilter,
  projectOptions,
  projectNames,
  onOpen,
  onNew,
  onTrash,
  onPin,
  empty,
}: NoteIndexProps) {
  const [sort, setSort] = useState<NotesSort>('updated');
  const [pinnedOnly, setPinnedOnly] = useState(false);
  const archived = listState === 'archived';

  const shown = useMemo(() => {
    const base = pinnedOnly ? notes.filter((n) => n.pinned) : notes;
    return sortNotes(base, sort);
  }, [notes, pinnedOnly, sort]);

  const noMatch = !empty && shown.length === 0;
  const hasProjects = projectOptions.length > 0;

  return (
    <div className="notes-index page-scaffold">
      <div className="notes-index-rail">
        <div className="notes-rail-tabs" role="group" aria-label="在用或归档">
          <button
            type="button"
            className={listState === 'active' ? 'is-on' : ''}
            aria-pressed={listState === 'active'}
            data-testid="notes-list-state-active"
            onClick={() => onListStateChange('active')}
          >
            在用
          </button>
          <button
            type="button"
            className={archived ? 'is-on' : ''}
            aria-pressed={archived}
            data-testid="notes-list-state-archived"
            onClick={() => onListStateChange('archived')}
          >
            归档
          </button>
        </div>

        <label className="notes-rail-search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={15} height={15} aria-hidden>
            <circle cx="11" cy="11" r="7" />
            <path d="M21 21l-4.3-4.3" />
          </svg>
          <input
            id="notes-search-input"
            type="text"
            role="searchbox"
            placeholder="找标题或摘要"
            value={searchQuery}
            onChange={(e) => onSearch(e.target.value)}
            autoComplete="off"
            aria-label="筛选笔记"
          />
        </label>

        {hasProjects ? (
          <GlassSelect
            size="sm"
            className="notes-rail-project"
            aria-label="按项目筛选"
            value={projectFilter}
            options={[{ value: '', label: '全部项目' }, ...projectOptions]}
            onChange={onProjectFilter}
          />
        ) : null}

        <div className="notes-rail-tools">
          <button
            type="button"
            className={`notes-rail-icon${pinnedOnly ? ' is-on' : ''}`}
            aria-pressed={pinnedOnly}
            aria-label={pinnedOnly ? '显示全部' : '只看置顶'}
            title={pinnedOnly ? '显示全部' : '只看置顶'}
            data-testid="notes-pinned-only"
            onClick={() => setPinnedOnly((v) => !v)}
          >
            <svg viewBox="0 0 24 24" fill={pinnedOnly ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" width={15} height={15} aria-hidden>
              <path d="M12 17v5M8 3h8l-1 7h3l-6 7-6-7h3L8 3z" />
            </svg>
          </button>
          <button
            type="button"
            className="notes-rail-sort"
            aria-label={sort === 'updated' ? '当前按最近更新，点击改为按标题' : '当前按标题，点击改为按最近更新'}
            title={sort === 'updated' ? '最近更新' : '按标题'}
            data-testid="notes-sort-btn"
            onClick={() => setSort((s) => (s === 'updated' ? 'title' : 'updated'))}
          >
            {sort === 'updated' ? '最近' : '标题'}
          </button>
          <div className="notes-rail-layout" role="group" aria-label="列表或卡片">
            <button
              type="button"
              className={layout === 'list' ? 'is-on' : ''}
              aria-pressed={layout === 'list'}
              aria-label="列表"
              onClick={() => onLayoutChange('list')}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
              </svg>
            </button>
            <button
              type="button"
              className={layout === 'card' ? 'is-on' : ''}
              aria-pressed={layout === 'card'}
              aria-label="卡片"
              onClick={() => onLayoutChange('card')}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                <rect x="3" y="3" width="7" height="7" rx="1" />
                <rect x="14" y="3" width="7" height="7" rx="1" />
                <rect x="3" y="14" width="7" height="7" rx="1" />
                <rect x="14" y="14" width="7" height="7" rx="1" />
              </svg>
            </button>
          </div>
          <button
            type="button"
            className="notes-rail-icon"
            aria-label="回收站"
            title="回收站"
            data-testid="notes-trash-btn"
            onClick={onTrash}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={15} height={15} aria-hidden>
              <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />
            </svg>
          </button>
          <button type="button" className="btn btn-primary btn-sm notes-rail-new" onClick={onNew} data-testid="notes-new-btn">
            新建
          </button>
        </div>
      </div>

      <div className="page-scaffold__body">
        {empty ? (
          <div className="page-scaffold__state">
            <EmptyState
              title={archived ? '没有归档笔记' : '还没有笔记'}
              icon={EmptyStateIcons.inbox}
              action={
                archived ? undefined : (
                  <button type="button" className="btn btn-primary" onClick={onNew}>
                    新建
                  </button>
                )
              }
            />
          </div>
        ) : noMatch ? (
          <div className="page-scaffold__state">
            <EmptyState
              title={pinnedOnly ? '没有置顶笔记' : '没有匹配的笔记'}
              icon={EmptyStateIcons.inbox}
            />
          </div>
        ) : layout === 'card' ? (
          <div className="notes-grid" data-testid="notes-card-grid">
            <NoteList notes={shown} projectNames={projectNames} variant="card" onSelect={onOpen} onPin={onPin} />
          </div>
        ) : (
          <div className="notes-index-list" data-testid="notes-row-list">
            <NoteList notes={shown} projectNames={projectNames} variant="list" onSelect={onOpen} onPin={onPin} />
          </div>
        )}
      </div>
    </div>
  );
}
