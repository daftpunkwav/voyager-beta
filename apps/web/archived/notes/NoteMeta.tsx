/** 笔记元信息栏:标签编辑(即时保存)、关联 source_id/node_id(link_note)、删除二次确认。 */

import { useEffect, useState } from 'react';
import { type Note, useNotesStore } from './notesStore';

export function NoteMeta() {
  const current = useNotesStore((s) => s.current);
  if (!current) {
    return <div className="note-meta note-meta--empty muted">未选择笔记。</div>;
  }
  return <MetaBody key={current.id} note={current} />;
}

function MetaBody({ note }: { note: Note }) {
  const save = useNotesStore((s) => s.save);
  const link = useNotesStore((s) => s.link);
  const remove = useNotesStore((s) => s.remove);
  const [tagText, setTagText] = useState(note.tags.join(', '));
  const [sourceId, setSourceId] = useState(note.source_id ?? '');
  const [nodeId, setNodeId] = useState(note.node_id ?? '');
  const [confirmDelete, setConfirmDelete] = useState(false);

  // 笔记被外部更新(如 agent 编辑)时同步展示
  useEffect(() => {
    setTagText(note.tags.join(', '));
  }, [note.tags]);

  const flushTags = () => {
    const tags = tagText.split(/[,，]/).map((t) => t.trim()).filter(Boolean);
    if (tags.join(',') !== note.tags.join(',')) void save(note.id, { tags });
  };

  return (
    <div className="note-meta">
      <div className="label">标签</div>
      <input
        className="setting-input"
        value={tagText}
        placeholder="逗号分隔"
        onChange={(e) => setTagText(e.target.value)}
        onBlur={flushTags}
      />

      <div className="label" style={{ marginTop: 12 }}>
        关联
      </div>
      <input
        className="setting-input"
        value={sourceId}
        placeholder="资源 source_id"
        onChange={(e) => setSourceId(e.target.value)}
        onBlur={() => {
          if (sourceId !== (note.source_id ?? '')) void link(note.id, sourceId, undefined);
        }}
      />
      <input
        className="setting-input"
        value={nodeId}
        placeholder="图谱节点 node_id"
        onChange={(e) => setNodeId(e.target.value)}
        onBlur={() => {
          if (nodeId !== (note.node_id ?? '')) void link(note.id, undefined, nodeId);
        }}
      />

      <div className="label" style={{ marginTop: 12 }}>
        信息
      </div>
      <div className="small muted mono">
        <div>id: {note.id}</div>
        <div>创建:{new Date(note.created_ts * 1000).toLocaleString()}</div>
        <div>更新:{new Date(note.updated_ts * 1000).toLocaleString()}</div>
      </div>

      <div style={{ marginTop: 'auto', paddingTop: 16 }}>
        {confirmDelete ? (
          <div className="note-meta__danger">
            <div className="small">删除不可恢复,确认?</div>
            <button type="button" className="btn" onClick={() => void remove(note.id)}>
              确认删除
            </button>
            <button type="button" className="btn" onClick={() => setConfirmDelete(false)}>
              取消
            </button>
          </div>
        ) : (
          <button type="button" className="btn" onClick={() => setConfirmDelete(true)}>
            删除笔记
          </button>
        )}
      </div>
    </div>
  );
}
