import { Link } from 'react-router-dom';
import type { Note } from '@/api/types';
import { formatDate, formatRelativeTime } from '@/utils/date';

interface NoteListProps {
  notes: Note[];
  projectNames: Map<string, string>;
  selectedId: string | null;
  onSelect: (note: Note) => void;
  variant?: 'default' | 'card';
}

function stripSnippet(content: string): string {
  return content.replace(/[#*`]/g, '').replace(/\s+/g, ' ').trim().slice(0, 80);
}

export function NoteList({ notes, projectNames, selectedId, onSelect, variant = 'card' }: NoteListProps) {
  if (notes.length === 0) {
    return <p className="muted" style={{ padding: 12 }}>暂无笔记</p>;
  }

  if (variant === 'default') {
    return (
      <>
        {notes.map((n) => (
          <button
            key={n.id}
            type="button"
            data-testid="note-item"
            className={`note-card ${selectedId === n.id ? 'active' : ''}`}
            onClick={() => onSelect(n)}
          >
            <div className="note-card-title">{n.title}</div>
            <div className="note-card-meta">
              <Link to={`/projects/${n.project_id}`} onClick={(e) => e.stopPropagation()}>
                {projectNames.get(n.project_id) ?? n.project_id}
              </Link>
              <span className="dot" />
              <span>{formatRelativeTime(n.updated_at)}</span>
            </div>
            <div className="note-card-snippet">{stripSnippet(n.content)}</div>
          </button>
        ))}
      </>
    );
  }

  return (
    <>
      {notes.map((n) => (
        <button
          key={n.id}
          type="button"
          data-testid="note-item"
          className={`note-card ${selectedId === n.id ? 'active' : ''}`}
          onClick={() => onSelect(n)}
        >
          <div className="note-card-title">{n.title}</div>
          <div className="note-card-meta">
            <span>{projectNames.get(n.project_id) ?? n.project_id}</span>
            <span className="dot" />
            <span>{formatDate(n.updated_at)}</span>
          </div>
          <div className="note-card-snippet">{stripSnippet(n.content)}</div>
        </button>
      ))}
    </>
  );
}
