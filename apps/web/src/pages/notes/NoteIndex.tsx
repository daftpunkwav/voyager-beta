/** 笔记首页:只列清单(列表 / 卡片),不打开编辑器。归档/删除/导出在条目与批量栏即可做。 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { GlassSelect } from '@/components/common/GlassSelect';
import type { Note } from '@/api/types';
import {
  applyNotesListing,
  groupNotesByRecency,
  noteSourceId,
} from './noteListing';
import {
  NOTES_FILTER_OPTIONS,
  NOTES_SORT_OPTIONS,
  type NotesDensity,
  type NotesFilter,
  type NotesLayout,
  type NotesListState,
  type NotesSort,
} from './notePrefs';
import { NotesAssistButton, NotesNewButton } from './NotesRailActions';
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
  onArchive: (ids: string[], archived: boolean) => void;
  onExport: (ids: string[]) => void;
  onDelete: (ids: string[]) => void;
  busy?: boolean;
  empty: boolean;
}

/** 与 notes.css `--notes-bulk-ms` 退场时长一致 */
const BULK_BAR_MS = 420;

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
  onArchive,
  onExport,
  onDelete,
  busy = false,
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

  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [selectMode, setSelectMode] = useState(false);
  const [menuId, setMenuId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<string[] | null>(null);
  const [bulkMounted, setBulkMounted] = useState(false);
  const [bulkExiting, setBulkExiting] = useState(false);
  const bulkCountRef = useRef(0);

  const stopSelecting = () => {
    setSelectMode(false);
    setSelected(new Set());
    setMenuId(null);
  };

  useEffect(() => {
    setSelected(new Set());
    setSelectMode(false);
    setMenuId(null);
  }, [listState, filter, sourceId]);

  useEffect(() => {
    const ids = new Set(shown.map((n) => n.id));
    setSelected((prev) => {
      let changed = false;
      const next = new Set<string>();
      for (const id of prev) {
        if (ids.has(id)) next.add(id);
        else changed = true;
      }
      return changed ? next : prev;
    });
  }, [shown]);

  useEffect(() => {
    if (!selectMode) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      e.preventDefault();
      setSelectMode(false);
      setSelected(new Set());
      setMenuId(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectMode]);

  const showBulk = selectMode && selected.size > 0;
  useEffect(() => {
    if (showBulk) {
      setBulkMounted(true);
      setBulkExiting(false);
      return undefined;
    }
    if (!bulkMounted) return undefined;
    const reduce = typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) {
      setBulkMounted(false);
      setBulkExiting(false);
      return undefined;
    }
    setBulkExiting(true);
    const t = window.setTimeout(() => {
      setBulkMounted(false);
      setBulkExiting(false);
    }, BULK_BAR_MS);
    return () => window.clearTimeout(t);
  }, [showBulk, bulkMounted]);

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectedIds = [...selected];
  const allShownSelected = shown.length > 0 && selected.size === shown.length;
  const selecting = selectMode;
  if (selected.size > 0) bulkCountRef.current = selected.size;

  const listProps = {
    projectNames,
    selectedIds: selected,
    menuId,
    selecting,
    archivedView: archived,
    density,
    onSelect: onOpen,
    onPin,
    onToggleSelect: selecting ? toggleSelect : undefined,
    onMenu: setMenuId,
    onArchive: (n: Note) => onArchive([n.id], !(n.archived || archived)),
    onExport: (n: Note) => onExport([n.id]),
    onDelete: (n: Note) => setPendingDelete([n.id]),
  };

  const noMatch = !empty && shown.length === 0;
  const filtered = filter !== 'all' || Boolean(query.trim()) || Boolean(sourceId);

  return (
    <>
    <div className={`notes-index page-scaffold${compact ? ' is-compact' : ''}${selecting ? ' is-selecting' : ''}`}>
      <div className="notes-index-rail">
        <div className="notes-rail-seg notes-rail-scope" role="tablist" aria-label="当前或归档">
          <button
            type="button"
            role="tab"
            className={listState === 'active' ? 'is-on' : ''}
            aria-selected={listState === 'active'}
            data-testid="notes-list-state-active"
            onClick={() => onListStateChange('active')}
          >
            当前
          </button>
          <button
            type="button"
            role="tab"
            className={archived ? 'is-on' : ''}
            aria-selected={archived}
            data-testid="notes-list-state-archived"
            onClick={() => onListStateChange('archived')}
          >
            归档
          </button>
        </div>

        <div className="notes-rail-find">
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
        </div>

        <div className="notes-rail-tools">
          <div className="notes-rail-cluster" role="group" aria-label="视图">
            <div className="notes-rail-seg notes-rail-view" role="group" aria-label="列表或卡片">
              <button
                type="button"
                className={layout === 'list' ? 'is-on' : ''}
                aria-pressed={layout === 'list'}
                aria-label="列表"
                title="列表"
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
                title="卡片"
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
            <div className="notes-rail-seg notes-rail-density" role="group" aria-label="疏密">
              <button
                type="button"
                className={!compact ? 'is-on' : ''}
                aria-pressed={!compact}
                data-testid="notes-density-comfortable"
                onClick={() => onDensity('comfortable')}
              >
                宽松
              </button>
              <button
                type="button"
                className={compact ? 'is-on' : ''}
                aria-pressed={compact}
                data-testid="notes-density-compact"
                onClick={() => onDensity('compact')}
              >
                紧凑
              </button>
            </div>
          </div>
          <span className="notes-rail-sep" aria-hidden />
          <div className="notes-rail-cluster notes-rail-batch-group" role="group" aria-label="批量">
            <button
              type="button"
              className={`notes-rail-batch${selectMode ? ' is-on' : ''}`}
              aria-pressed={selectMode}
              aria-label={selectMode ? '完成' : '批量'}
              data-testid="notes-select-btn"
              onClick={() => (selectMode ? stopSelecting() : setSelectMode(true))}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={14} height={14} aria-hidden>
                <rect x="3" y="4" width="4" height="4" rx="1" />
                <path d="M10 6h11" />
                <rect x="3" y="10" width="4" height="4" rx="1" />
                <path d="M10 12h11" />
                <rect x="3" y="16" width="4" height="4" rx="1" />
                <path d="M10 18h11" />
              </svg>
              <span className="notes-rail-swap">
                <span className={selectMode ? 'is-leave' : 'is-here'} aria-hidden={selectMode}>批量</span>
                <span className={selectMode ? 'is-here' : 'is-leave'} aria-hidden={!selectMode}>完成</span>
              </span>
            </button>
            <div className={`notes-rail-allslot${selectMode ? ' is-open' : ''}`} inert={!selectMode}>
              <div className="notes-rail-allslot__inner">
                <button
                  type="button"
                  className="notes-rail-batch notes-rail-all"
                  disabled={!selectMode || busy || shown.length === 0}
                  aria-label={allShownSelected ? '取消全选' : '全选'}
                  data-testid="notes-bulk-select-all"
                  onClick={() => setSelected(allShownSelected ? new Set() : new Set(shown.map((n) => n.id)))}
                >
                  <span className="notes-rail-swap">
                    <span className={allShownSelected ? 'is-leave' : 'is-here'} aria-hidden={allShownSelected}>全选</span>
                    <span className={allShownSelected ? 'is-here' : 'is-leave'} aria-hidden={!allShownSelected}>取消全选</span>
                  </span>
                </button>
              </div>
            </div>
          </div>
          <span className="notes-rail-sep" aria-hidden />
          <div className="notes-rail-cluster notes-rail-actions">
            <NotesAssistButton onClick={onAssist} />
            <button
              type="button"
              className="notes-rail-trash glass-card glass-card--control liquid-glass--pill"
              aria-label="回收站"
              title="回收站"
              data-testid="notes-trash-btn"
              onClick={onTrash}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={15} height={15} aria-hidden>
                <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />
              </svg>
            </button>
            <NotesNewButton onClick={onNew} />
          </div>
        </div>
      </div>

      <div className="page-scaffold__body">
        {bulkMounted ? (
          <div
            className={`notes-bulk${bulkExiting ? ' is-exit' : ''}`}
            role="region"
            aria-label="已选笔记"
            data-testid="notes-bulk-bar"
          >
            <span className="notes-bulk__count" aria-live="polite">
              已选 <strong>{selected.size || bulkCountRef.current}</strong> 篇
            </span>
            <div className="notes-bulk__actions">
              <button
                type="button"
                className="notes-bulk__btn"
                disabled={busy}
                data-testid="notes-bulk-archive"
                onClick={() => onArchive(selectedIds, !archived)}
              >
                {archived ? '取消归档' : '归档'}
              </button>
              <button
                type="button"
                className="notes-bulk__btn"
                disabled={busy}
                data-testid="notes-bulk-export"
                onClick={() => onExport(selectedIds)}
              >
                导出
              </button>
              <button
                type="button"
                className="notes-bulk__btn is-danger"
                disabled={busy}
                data-testid="notes-bulk-delete"
                onClick={() => setPendingDelete(selectedIds)}
              >
                移入回收站
              </button>
              <button
                type="button"
                className="notes-bulk__btn"
                disabled={busy}
                data-testid="notes-bulk-clear"
                onClick={() => setSelected(new Set())}
              >
                取消选择
              </button>
            </div>
          </div>
        ) : null}
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
            <NoteList notes={shown} variant="card" {...listProps} />
          </div>
        ) : (
          <div className="notes-index-list" data-testid="notes-row-list">
            {buckets && buckets.length > 1 ? (
              buckets.map((b) => (
                <section key={b.id} className="notes-index-bucket">
                  <h3 className="notes-index-bucket__label">{b.label}</h3>
                  <NoteList notes={b.items} variant="list" {...listProps} />
                </section>
              ))
            ) : (
              <NoteList notes={shown} variant="list" {...listProps} />
            )}
          </div>
        )}
      </div>
    </div>
    <ConfirmDialog
      open={Boolean(pendingDelete?.length)}
      title="移入回收站"
      message={
        pendingDelete && pendingDelete.length > 1
          ? `确定将 ${pendingDelete.length} 篇笔记移入回收站?之后可在回收站恢复。`
          : '确定将此笔记移入回收站?之后可在回收站恢复。'
      }
      confirmLabel="移入回收站"
      danger
      onConfirm={() => {
        if (pendingDelete?.length) onDelete(pendingDelete);
        setPendingDelete(null);
      }}
      onCancel={() => setPendingDelete(null)}
    />
    </>
  );
}
