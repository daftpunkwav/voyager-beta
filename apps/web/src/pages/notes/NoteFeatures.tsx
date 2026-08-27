/** 笔记功能面组件:版本历史抽屉 / 回收站面板 / TOC 大纲 / 反链列表。
 *  页面私有组件(§10.1),只被 NotesPage 使用;数据全部来自既有后端能力。
 */

import { useState } from 'react';
import GithubSlugger from 'github-slugger';
import {
  useBacklinks,
  useEmptyTrash,
  useNoteToc,
  useNoteVersions,
  usePurgeNote,
  useRestoreNote,
  useRestoreVersion,
  useTrashNotes,
} from '@/hooks/useNotes';
import { useUIStore } from '@/stores/uiStore';

/** 版本历史抽屉:列举 → 选版对比(字符数) → 回退(回退本身再成快照)。 */
export function VersionDrawer({ noteId, open, onClose }: { noteId: string; open: boolean; onClose: () => void }) {
  const { data, isLoading } = useNoteVersions(noteId, open);
  const restore = useRestoreVersion();
  const [selected, setSelected] = useState<number | null>(null);
  const addToast = useUIStore((s) => s.addToast);
  if (!open) return null;
  return (
    <div className="drawer-overlay" onClick={onClose}>
      <aside className="drawer version-drawer" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="版本历史">
        <header className="version-drawer__head">
          <h3>版本历史</h3>
          <button type="button" className="icon-btn" aria-label="关闭" onClick={onClose}>✕</button>
        </header>
        {isLoading ? (
          <p className="muted">加载中…</p>
        ) : !data || data.versions.length === 0 ? (
          <p className="muted">还没有历史版本;内容每次实质保存都会自动快照。</p>
        ) : (
          <ul className="version-drawer__list">
            {data.versions.map((v) => (
              <li
                key={v.version}
                className={`version-drawer__item ${selected === v.version ? 'is-active' : ''}`}
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
          <footer className="version-drawer__foot">
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
    </div>
  );
}

/** 回收站:恢复 / 彻底删 / 清空(全带确认语义的不可逆操作集中处理)。 */
export function TrashPanel({ open, onClose, onOpenNote }: { open: boolean; onClose: () => void; onOpenNote: (id: string) => void }) {
  const { data: notes = [] } = useTrashNotes(open);
  const restore = useRestoreNote();
  const purge = usePurgeNote();
  const empty = useEmptyTrash();
  const addToast = useUIStore((s) => s.addToast);
  if (!open) return null;
  return (
    <div className="drawer-overlay" onClick={onClose}>
      <aside className="drawer trash-panel" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="回收站">
        <header className="version-drawer__head">
          <h3>回收站({notes.length})</h3>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            <button
              type="button"
              className="btn btn-sm"
              disabled={notes.length === 0 || empty.isPending}
              onClick={() => {
                if (window.confirm('彻底清空回收站?此操作不可撤销。')) {
                  empty.mutate(undefined, { onSuccess: () => addToast({ type: 'success', message: '回收站已清空' }) });
                }
              }}
            >
              清空
            </button>
            <button type="button" className="icon-btn" aria-label="关闭" onClick={onClose}>✕</button>
          </div>
        </header>
        {notes.length === 0 ? (
          <p className="muted">回收站是空的。</p>
        ) : (
          <ul className="version-drawer__list">
            {notes.map((n) => (
              <li key={n.id} className="version-drawer__item">
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
                      onClick={() => {
                        if (window.confirm(`彻底删除「${n.title || '无标题'}」?版本与关联会一并清除,不可撤销。`)) {
                          purge.mutate(n.id, { onSuccess: () => addToast({ type: 'success', message: '已彻底删除' }) });
                        }
                      }}
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
  );
}

/** TOC 大纲:后端 get_note_toc(跳过代码围栏);点击滚动到对应标题锚点。 */
export function TocPanel({ noteId }: { noteId: string }) {
  const { data } = useNoteToc(noteId);
  const toc = data?.toc ?? [];
  if (toc.length === 0) return null;
  return (
    <nav className="toc-panel" aria-label="目录">
      <h4 className="small muted">大纲</h4>
      <ul>
        {toc.map((h, i) => (
          <li key={`${i}-${h.text}`} style={{ paddingLeft: (h.level - 1) * 12 }}>
            <a
              href={`#${slugify(h.text)}`}
              onClick={(e) => {
                e.preventDefault();
                document
                  .getElementById(slugify(h.text))
                  ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
              }}
            >
              {h.text}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** 反链:引用了当前笔记的笔记;点击跳转。 */
export function BacklinkPanel({ noteId }: { noteId: string }) {
  const { data } = useBacklinks(noteId);
  const backlinks = data?.backlinks ?? [];
  if (backlinks.length === 0) return null;
  return (
    <div className="backlink-panel">
      <h4 className="small muted">反链({backlinks.length})</h4>
      <ul>
        {backlinks.map((b) => (
          <li key={b.id}>
            <a href={`/notes?note=${b.id}`}>{b.title}</a>
          </li>
        ))}
      </ul>
    </div>
  );
}

// 与 MarkdownRenderer 共用 github-slugger 单实例,避免重复标题 slug 不一致。
const _slugger = new GithubSlugger();
function slugify(text: string): string {
  return _slugger.slug(text);
}
