/** 笔记摘要列表:标签筛选 + 摘要(excerpt 服务端生成)+ 新建。 */

import { visibleSummaries, useNotesStore } from './notesStore';

export function NoteList() {
  const state = useNotesStore();
  const visible = visibleSummaries(state);
  const allTags = [...new Set(state.summaries.flatMap((s) => s.tags))].sort();

  return (
    <div className="note-list">
      <div className="note-list__head">
        <button type="button" className="btn btn-primary" onClick={() => void state.create()}>
          新建笔记
        </button>
      </div>
      {allTags.length > 0 ? (
        <div className="note-tags">
          <button
            type="button"
            className={`tag-chip ${state.filterTag === '' ? 'tag-chip--active' : ''}`}
            onClick={() => state.setFilterTag('')}
          >
            全部
          </button>
          {allTags.map((t) => (
            <button
              key={t}
              type="button"
              className={`tag-chip ${state.filterTag === t ? 'tag-chip--active' : ''}`}
              onClick={() => state.setFilterTag(t)}
            >
              {t}
            </button>
          ))}
        </div>
      ) : null}
      <div className="note-list__items">
        {visible.length === 0 ? (
          <p className="muted small">还没有笔记;点"新建笔记"或让 Lucien 帮你记。</p>
        ) : null}
        {visible.map((s) => (
          <button
            key={s.id}
            type="button"
            className={`note-item ${state.current?.id === s.id ? 'note-item--active' : ''}`}
            onClick={() => void state.open(s.id)}
          >
            <div className="note-item__title">{s.title}</div>
            <div className="note-item__excerpt small muted">{s.excerpt}</div>
            <div className="note-item__meta small muted">
              {s.tags.map((t) => `#${t}`).join(' ') || ''}
              {s.tags.length > 0 ? ' · ' : ''}
              {new Date(s.updated_ts * 1000).toLocaleString()}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
