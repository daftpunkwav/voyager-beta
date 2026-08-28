/** 版本历史:居中液态玻璃弹窗,与回收站同一套 modal。 */

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNoteVersions, useRestoreVersion } from '@/hooks/useNotes';
import { useUIStore } from '@/stores/uiStore';

export function VersionPanel({ noteId, open, onClose }: { noteId: string; open: boolean; onClose: () => void }) {
  const { data, isLoading } = useNoteVersions(noteId, open);
  const restore = useRestoreVersion();
  const [selected, setSelected] = useState<number | null>(null);
  const addToast = useUIStore((s) => s.addToast);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  useEffect(() => {
    if (!open) setSelected(null);
  }, [open]);
  if (!open) return null;
  return createPortal(
    <div className="modal-overlay" role="presentation" onClick={onClose}>
      <aside
        className="modal modal--wide notes-dialog glass-card glass-card--dialog"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="版本历史"
      >
        <header className="notes-dialog__head">
          <h3>版本历史</h3>
          <button type="button" className="icon-btn" aria-label="关闭" onClick={onClose}>✕</button>
        </header>
        {isLoading ? (
          <p className="muted">加载中…</p>
        ) : !data || data.versions.length === 0 ? (
          <p className="muted">还没有历史版本;内容每次实质保存都会自动快照。</p>
        ) : (
          <ul className="notes-dialog__list">
            {data.versions.map((v) => (
              <li
                key={v.version}
                className={`notes-dialog__item ${selected === v.version ? 'is-active' : ''}`}
              >
                <button type="button" onClick={() => setSelected(v.version)}>
                  <span>版本 {v.version}</span>
                  <span className="muted small">
                    {new Date(v.ts * 1000).toLocaleString('zh-CN')} · {v.chars} 字
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {selected !== null && (
          <footer className="notes-dialog__foot">
            <span className="muted small">将回退到版本 {selected}(当前内容会先自动快照)</span>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={restore.isPending}
              onClick={() =>
                restore.mutate(
                  { id: noteId, version: selected },
                  {
                    onSuccess: () => {
                      addToast({ type: 'success', message: `已回退到版本 ${selected}` });
                      onClose();
                    },
                    onError: (e) => addToast({ type: 'error', message: e instanceof Error ? e.message : '回退失败' }),
                  },
                )
              }
            >
              回退到此版本
            </button>
          </footer>
        )}
      </aside>
    </div>,
    document.body,
  );
}
