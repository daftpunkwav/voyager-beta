import type { KeyboardEvent } from 'react';
import type { Note } from '@/api/types';
import { noteSnippet, noteSourceId, noteUpdatedLabel, type NotesDensity } from './noteUtils';

interface NoteListProps {
  notes: Note[];
  projectNames?: Map<string, string>;
  selectedId?: string | null;
  onSelect: (note: Note) => void;
  onPin?: (note: Note, pinned: boolean) => void;
  emptyLabel?: string;
  variant?: 'list' | 'card';
  density?: NotesDensity;
}

function PinButton({
  pinned,
  onClick,
}: {
  pinned: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`note-pin${pinned ? ' is-on' : ''}`}
      aria-label={pinned ? '取消置顶' : '置顶'}
      aria-pressed={pinned}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
    >
      <svg viewBox="0 0 24 24" fill={pinned ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" width={14} height={14} aria-hidden>
        <path d="M12 17v5M8 3h8l-1 7h3l-6 7-6-7h3L8 3z" />
      </svg>
    </button>
  );
}

export function NoteList({
  notes,
  projectNames,
  selectedId,
  onSelect,
  onPin,
  emptyLabel = '暂无笔记',
  variant = 'list',
  density = 'comfortable',
}: NoteListProps) {
  const snip = density === 'compact' ? 72 : variant === 'card' ? 160 : 120;
  if (notes.length === 0) {
    return <p className="muted notes-list-empty">{emptyLabel}</p>;
  }

  return (
    <>
      {notes.map((n) => {
        const src = noteSourceId(n);
        const name = projectNames?.get(src) ?? src;
        const projectLabel = src ? name || '未命名项目' : '';
        const snippet = noteSnippet(n);
        const time = noteUpdatedLabel(n);
        const pinned = Boolean(n.pinned);
        const onKey = (e: KeyboardEvent) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onSelect(n);
          }
        };
        if (variant === 'card') {
          return (
            <div
              key={n.id}
              role="button"
              tabIndex={0}
              data-testid="note-item"
              className={`note-grid-card${selectedId === n.id ? ' active' : ''}${pinned ? ' is-pinned' : ''}`}
              onClick={() => onSelect(n)}
              onKeyDown={onKey}
            >
              {onPin ? <PinButton pinned={pinned} onClick={() => onPin(n, !pinned)} /> : null}
              {projectLabel ? <span className="project-tag">{projectLabel}</span> : null}
              <h4>{n.title || '无标题'}</h4>
              {snippet ? <p className="snippet">{snippet.slice(0, snip)}</p> : <p className="snippet muted">无摘要</p>}
              <div className="meta">
                <span>{time || '刚刚'}</span>
              </div>
            </div>
          );
        }
        return (
          <div
            key={n.id}
            role="button"
            tabIndex={0}
            data-testid="note-item"
            className={`note-row${selectedId === n.id ? ' active' : ''}${pinned ? ' is-pinned' : ''}`}
            onClick={() => onSelect(n)}
            onKeyDown={onKey}
          >
            {onPin ? <PinButton pinned={pinned} onClick={() => onPin(n, !pinned)} /> : <span className="note-pin-slot" />}
            <div className="note-row-title">{n.title || '无标题'}</div>
            <div className="note-row-snippet">{snippet ? snippet.slice(0, snip) : '无摘要'}</div>
            <div className="note-row-project">{projectLabel || '—'}</div>
            <div className="note-row-time">{time || '—'}</div>
          </div>
        );
      })}
    </>
  );
}
