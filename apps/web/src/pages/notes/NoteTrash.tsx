/** 回收站:居中弹窗,恢复 / 彻底删 / 清空;危险确认走 ConfirmDialog。 */

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { useEmptyTrash, usePurgeNote, useRestoreNote, useTrashNotes } from '@/hooks/useNotes';
import { useUIStore } from '@/stores/uiStore';

type Pending =
  | { kind: 'empty' }
  | { kind: 'purge'; id: string; title: string }
  | null;

export function TrashPanel({ open, onClose, onOpenNote }: { open: boolean; onClose: () => void; onOpenNote: (id: string) => void }) {
  const { data: notes = [] } = useTrashNotes(open);
  const restore = useRestoreNote();
  const purge = usePurgeNote();
  const empty = useEmptyTrash();
  const addToast = useUIStore((s) => s.addToast);
  const [pending, setPending] = useState<Pending>(null);

  useEffect(() => {
    if (!open) {
      setPending(null);
      return;
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !pending) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose, pending]);

  if (!open) return null;
  return createPortal(
    <>
      <div className="modal-overlay" role="presentation" onClick={onClose}>
        <aside
          className="modal modal--wide notes-dialog trash-panel glass-card glass-card--dialog"
          onClick={(e) => e.stopPropagation()}
          role="dialog"
          aria-modal="true"
          aria-label="回收站"
        >
          <header className="notes-dialog__head">
            <h3>回收站({notes.length})</h3>
            <div className="trash-panel__head-actions">
              <button
                type="button"
                className="btn btn-sm btn-danger trash-panel__purge"
                disabled={notes.length === 0 || empty.isPending}
                onClick={() => setPending({ kind: 'empty' })}
              >
                清空
              </button>
              <button type="button" className="icon-btn" aria-label="关闭" onClick={onClose}>✕</button>
            </div>
          </header>
          {notes.length === 0 ? (
            <p className="trash-panel__empty">回收站是空的</p>
          ) : (
            <ul className="notes-dialog__list">
              {notes.map((n) => (
                <li key={n.id} className="notes-dialog__item">
                  <div className="trash-panel__row">
                    <span className="trash-panel__title">{n.title || '无标题'}</span>
                    <span className="trash-panel__actions">
                      <button
                        type="button"
                        className="btn btn-sm"
                        onClick={() =>
                          restore.mutate(n.id, {
                            onSuccess: () => {
                              addToast({ type: 'success', message: '已恢复' });
                              onOpenNote(n.id);
                            },
                          })
                        }
                      >
                        恢复
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm bulk-bar__btn--danger"
                        onClick={() => setPending({ kind: 'purge', id: n.id, title: n.title || '无标题' })}
                      >
                        彻底删除
                      </button>
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
      <ConfirmDialog
        open={pending?.kind === 'empty'}
        title="清空回收站"
        message="彻底清空回收站?此操作不可撤销。"
        confirmLabel="清空"
        danger
        onConfirm={() => {
          empty.mutate(undefined, { onSuccess: () => addToast({ type: 'success', message: '回收站已清空' }) });
          setPending(null);
        }}
        onCancel={() => setPending(null)}
      />
      <ConfirmDialog
        open={pending?.kind === 'purge'}
        title="彻底删除"
        message={`彻底删除「${pending?.kind === 'purge' ? pending.title : ''}」?版本与关联会一并清除,不可撤销。`}
        confirmLabel="彻底删除"
        danger
        onConfirm={() => {
          if (pending?.kind === 'purge') {
            purge.mutate(pending.id, { onSuccess: () => addToast({ type: 'success', message: '已彻底删除' }) });
          }
          setPending(null);
        }}
        onCancel={() => setPending(null)}
      />
    </>,
    document.body,
  );
}
