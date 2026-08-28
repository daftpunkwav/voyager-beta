/** 笔记首页:只列清单(列表 / 卡片),不打开编辑器。 */

import { useMemo } from 'react';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { GlassSelect } from '@/components/common/GlassSelect';
import { personaDisplayName } from '@/constants/personas';
import type { Note } from '@/api/types';
import {
  applyNotesListing,
  groupNotesByRecency,
  noteSourceId,
  NOTES_FILTER_OPTIONS,
  NOTES_SORT_OPTIONS,
  type NotesDensity,
  type NotesFilter,
  type NotesLayout,
  type NotesListState,
  type NotesSort,
} from './noteUtils';
import { NoteList } from './NoteList';

interface NoteIndexProps {
  notes: Note[];
  layout: NotesLayout;
  listState: NotesListState;
  onLayoutChange: (layout: NotesLayout) => void;
  onListStateChange: (state: NotesListState) => void;
  query: string;
  onQuery: (q: string) => void;
  sort: NotesSort;
  onSort: (sort: NotesSort) => void;
  filter: NotesFilter;
  onFilter: (filter: NotesFilter) => void;
  sourceId: string;
  onSourceId: (id: string) => void;
  density: NotesDensity;
  onDensity: (density: NotesDensity) => void;
  projectOptions: { value: string; label: string }[];
  projectNames: Map<string, string>;
  onOpen: (note: Note) => void;
  onNew: () => void;
  onTrash: () => void;
  onAssist: () => void;
  onPin: (note: Note, pinned: boolean) => void;
  empty: boolean;
}

export function NoteIndex({
  notes,
  layout,
  listState,
  onLayoutChange,
  onListStateChange,
  query,
  onQuery,
  sort,
  onSort,
  filter,
  onFilter,
  sourceId,
  onSourceId,
  density,
  onDensity,
  projectOptions,
  projectNames,
  onOpen,
  onNew,
  onTrash,
  onAssist,
  onPin,
  empty,
}: NoteIndexProps) {
  const archived = listState === 'archived';
  const compact = density === 'compact';
  const hasProjects = projectOptions.length > 0;

  const shown = useMemo(
    () =>
      applyNotesListing(notes, {
        query,
        filter,
        sort,
        sourceId,
        extraText: (n) => projectNames.get(noteSourceId(n)) ?? '',
      }),
    [notes, query, filter, sort, sourceId, projectNames],
  );

  const buckets = useMemo(() => {
    if (layout !== 'list' || sort === 'title') return null;
    return groupNotesByRecency(shown, sort === 'created' ? 'created' : 'updated');
  }, [layout, sort, shown]);

  const noMatch = !empty && shown.length === 0;
  const filtered = filter !== 'all' || Boolean(query.trim()) || Boolean(sourceId);

  return (
    <div className={`notes-index page-scaffold${compact ? ' is-compact' : ''}`}>
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
            value={query}
            onChange={(e) => onQuery(e.target.value)}
            autoComplete="off"
            aria-label="筛选笔记"
          />
        </label>

        <GlassSelect
          size="sm"
          className="notes-rail-filter"
          aria-label="筛选"
          value={filter}
          options={NOTES_FILTER_OPTIONS}
          onChange={(v) => onFilter(v as NotesFilter)}
        />
        <GlassSelect
          size="sm"
          className="notes-rail-order"
          aria-label="排序"
          value={sort}
          options={NOTES_SORT_OPTIONS}
          onChange={(v) => onSort(v as NotesSort)}
        />
        {hasProjects ? (
          <GlassSelect
            size="sm"
            className="notes-rail-project"
            aria-label="按项目筛选"
            value={sourceId}
            options={[{ value: '', label: '全部项目' }, ...projectOptions]}
            onChange={onSourceId}
          />
        ) : null}

        <div className="notes-rail-tools">
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
            className={`notes-rail-icon${compact ? ' is-on' : ''}`}
            aria-pressed={compact}
            aria-label={compact ? '宽松间距' : '紧凑间距'}
            title={compact ? '宽松' : '紧凑'}
            data-testid="notes-density-btn"
            onClick={() => onDensity(compact ? 'comfortable' : 'compact')}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={15} height={15} aria-hidden>
              <path d="M4 8h16M4 12h16M4 16h16" />
            </svg>
          </button>
          <button
            type="button"
            className="notes-rail-assist"
            aria-label={`打开 ${personaDisplayName('organizer')}`}
            data-testid="notes-assist-btn"
            onClick={onAssist}
          >
            {personaDisplayName('organizer')}
          </button>
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
              title={filtered ? '没有匹配的笔记' : '没有笔记'}
              icon={EmptyStateIcons.inbox}
            />
          </div>
        ) : layout === 'card' ? (
          <div className="notes-grid" data-testid="notes-card-grid">
            <NoteList notes={shown} projectNames={projectNames} variant="card" density={density} onSelect={onOpen} onPin={onPin} />
          </div>
        ) : (
          <div className="notes-index-list" data-testid="notes-row-list">
            {buckets && buckets.length > 1 ? (
              buckets.map((b) => (
                <section key={b.id} className="notes-index-bucket">
                  <h3 className="notes-index-bucket__label">{b.label}</h3>
                  <NoteList notes={b.items} projectNames={projectNames} variant="list" density={density} onSelect={onOpen} onPin={onPin} />
                </section>
              ))
            ) : (
              <NoteList notes={shown} projectNames={projectNames} variant="list" density={density} onSelect={onOpen} onPin={onPin} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
