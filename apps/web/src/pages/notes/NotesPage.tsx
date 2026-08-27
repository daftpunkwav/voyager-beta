import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  fetchNoteFull,
  useAllNotes,
  useCreateNote,
  useDeleteNote,
  useUpdateNote,
} from '@/hooks/useNotes';
import { useProjects } from '@/hooks/useProjects';
import { useNoteStore } from '@/stores/noteStore';
import { useUIStore } from '@/stores/uiStore';
import { getApi } from '@/api/client';
import { consumeAgentSSEStream } from '@/utils/agentSSEStream';
import { NoteList } from '@/components/note/NoteList';
import { NoteEditor } from '@/components/note/NoteEditor';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { BacklinkPanel, TocPanel, TrashPanel, VersionDrawer } from './NoteFeatures';

type NotesView = 'split' | 'list-only' | 'edit-only' | 'preview-only';

/** 新建草稿 id 为 'new'；其余（UUID / mock n_*）均视为已有笔记 */
function isPersistedNoteId(id: string | null | undefined): id is string {
  return Boolean(id && id !== 'new');
}

export function NotesPage() {
  const [searchParams] = useSearchParams();
  const { data: notes = [], isLoading } = useAllNotes();
  const { data: projectsData } = useProjects();
  const searchQuery = useNoteStore((s) => s.searchQuery);
  const setSearchQuery = useNoteStore((s) => s.setSearchQuery);
  const selectedNoteId = useNoteStore((s) => s.selectedNoteId);
  const editorContent = useNoteStore((s) => s.editorContent);
  const editorTitle = useNoteStore((s) => s.editorTitle);
  const startEditing = useNoteStore((s) => s.startEditing);
  const setEditorContent = useNoteStore((s) => s.setEditorContent);
  const setEditorTitle = useNoteStore((s) => s.setEditorTitle);
  const editingNoteId = useNoteStore((s) => s.editingNoteId);
  const createNote = useCreateNote();
  const updateNote = useUpdateNote();
  const deleteNote = useDeleteNote();
  const addToast = useUIStore((s) => s.addToast);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [newProjectId, setNewProjectId] = useState(
    () => searchParams.get('project') ?? ''
  );
  const [trashOpen, setTrashOpen] = useState(false);
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [saveState, setSaveState] = useState<'saved' | 'unsaved' | 'saving'>('saved');
  const dirtyRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const doSave = useCallback(async () => {
    const t = useNoteStore.getState().editorTitle;
    const c = useNoteStore.getState().editorContent;
    if (!t.trim()) return;
    const id = useNoteStore.getState().editingNoteId;
    setSaveState('saving');
    try {
      if (isPersistedNoteId(id)) {
        await updateNote.mutateAsync({ id, title: t, content: c });
      } else if (newProjectId) {
        await createNote.mutateAsync({ projectId: newProjectId, title: t, content: c });
      } else {
        setSaveState('unsaved');
        return;
      }
      dirtyRef.current = false;
      setSaveState('saved');
    } catch (err) {
      setSaveState('unsaved');
      addToast({ type: 'error', message: err instanceof Error ? err.message : '保存失败' });
    }
  }, [updateNote, createNote, newProjectId, addToast]);

  // 自动保存:编辑置脏 → debounce(5s)落盘;关页/切笔记前 flush
  const markDirty = useCallback(() => {
    dirtyRef.current = true;
    setSaveState('unsaved');
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => void doSave(), 5000);
  }, [doSave]);

  // 编辑动作置脏:startEditing 初载(切笔记/回退)不视为编辑
  const loadedFor = useRef<string | null>(null);
  useEffect(() => {
    if (loadedFor.current !== editingNoteId) {
      loadedFor.current = editingNoteId;
      return;
    }
    markDirty();
  }, [editorContent, editorTitle, editingNoteId, markDirty]);

  useEffect(() => {
    const flush = () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (dirtyRef.current && isPersistedNoteId(editingNoteId)) void doSave();
    };
    window.addEventListener('beforeunload', flush);
    return () => {
      window.removeEventListener('beforeunload', flush);
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [doSave, editingNoteId]);
  const [view, setView] = useState<NotesView>('split');
  const [scribeStreaming, setScribeStreaming] = useState(false);

  // Agent 结果卡深链：/notes?note=<id>&project=<id>
  useEffect(() => {
    const noteId = searchParams.get('note');
    if (!noteId || isLoading) return;
    if (editingNoteId === noteId) return;
    const note = notes.find((n) => n.id === noteId);
    if (!note) return;
    startEditing(note.id, note.title, note.content ?? '');
    setNewProjectId(note.project_id);
  }, [searchParams, notes, isLoading, editingNoteId, startEditing]);

  // URL 仅带 project 时预填新建关联
  useEffect(() => {
    const projectId = searchParams.get('project');
    if (!projectId || searchParams.get('note')) return;
    if (!newProjectId) setNewProjectId(projectId);
  }, [searchParams, newProjectId]);

  const projectNames = useMemo(() => {
    const m = new Map<string, string>();
    for (const p of projectsData?.items ?? []) {
      m.set(p.id, p.name);
    }
    return m;
  }, [projectsData]);

  const filtered = useMemo(() => {
    const q = searchQuery.toLowerCase();
    if (!q) return notes;
    return notes.filter(
      (n) =>
        n.title.toLowerCase().includes(q) ||
        n.content.toLowerCase().includes(q) ||
        (projectNames.get(n.project_id) ?? '').toLowerCase().includes(q)
    );
  }, [notes, searchQuery, projectNames]);

  const projectCount = useMemo(() => {
    const ids = new Set(notes.map((n) => n.project_id));
    return ids.size;
  }, [notes]);

  const handleNew = () => {
    startEditing('new', '新笔记', '');
    setNewProjectId(
      searchParams.get('project') || projectsData?.items[0]?.id || ''
    );
    dirtyRef.current = false;
    setSaveState('unsaved');
  };

  const runScribe = async () => {
    const projectId =
      newProjectId ||
      notes.find((n) => n.id === editingNoteId)?.project_id ||
      searchParams.get('project') ||
      projectsData?.items[0]?.id;
    if (!projectId) {
      addToast({ type: 'warning', message: '请先选择关联项目' });
      return;
    }
    if (!editingNoteId) {
      startEditing('new', 'Scribe 笔记草稿', '');
      setNewProjectId(projectId);
    }
    setScribeStreaming(true);
    let buf = '';
    try {
      const stream = getApi().generateNote(projectId, {
        mode: 'project',
        topic: editorTitle || undefined,
      });
      await consumeAgentSSEStream(stream, {
        onTextDelta: (_piece, fullText) => {
          buf = fullText;
          setEditorContent(fullText);
          if (fullText.startsWith('# ')) {
            const firstLine = fullText.split('\n')[0]?.replace(/^#\s*/, '').trim();
            if (firstLine) setEditorTitle(firstLine.slice(0, 80));
          }
        },
        onError: (msg) => {
          addToast({ type: 'error', message: msg });
        },
      });
      if (buf.trim()) {
        addToast({ type: 'success', message: 'Scribe 已生成笔记草稿' });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Scribe 生成失败';
      addToast({ type: 'error', message });
    } finally {
      setScribeStreaming(false);
    }
  };

  const handleSave = async () => {
    if (!useNoteStore.getState().editorTitle.trim()) {
      addToast({ type: 'warning', message: '请输入标题' });
      return;
    }
    if (timerRef.current) clearTimeout(timerRef.current);
    await doSave();
  };

  if (isLoading) return <LoadingSpinner fullScreen />;

  return (
    <div className="notes-shell" data-view={view}>
      <header className="notes-topbar">
        <div className="notes-search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={14} height={14}>
            <circle cx="11" cy="11" r="7" />
            <path d="M21 21l-4.3-4.3" />
          </svg>
          <input
            type="text"
            placeholder="搜索笔记标题、内容..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <kbd>⌘K</kbd>
        </div>
        <button type="button" className="btn btn-primary btn-sm" onClick={handleNew}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={14} height={14}>
            <path d="M12 5v14M5 12h14" />
          </svg>
          新建笔记
        </button>
        <button
          type="button"
          className="btn btn-sm"
          disabled={scribeStreaming}
          onClick={() => void runScribe()}
          title="由 Scribe Agent 生成大纲与草稿"
        >
          {scribeStreaming ? 'Scribe 生成中…' : 'Scribe 辅助'}
        </button>
        <div className="view-toggle" role="tablist">
          {(
            [
              ['list-only', '列表视图'],
              ['split', '分屏'],
              ['edit-only', '仅编辑'],
              ['preview-only', '仅预览'],
            ] as const
          ).map(([v, title]) => (
            <button
              key={v}
              type="button"
              className={`view-btn ${view === v ? 'active' : ''}`}
              title={title}
              onClick={() => setView(v)}
            >
              {v === 'split' && (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={14} height={14}>
                  <rect x="3" y="3" width="8" height="18" rx="1" />
                  <rect x="13" y="3" width="8" height="18" rx="1" />
                </svg>
              )}
              {v === 'edit-only' && (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={14} height={14}>
                  <path d="M12 20h9M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z" />
                </svg>
              )}
              {v === 'preview-only' && (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={14} height={14}>
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
              )}
              {v === 'list-only' && (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={14} height={14}>
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <path d="M3 9h18M3 15h18" />
                </svg>
              )}
            </button>
          ))}
        </div>
        {editingNoteId && (
          <div className={`save-indicator ${saveState === 'saved' ? 'saved' : 'saving'}`}>
            <span className="dot" />
            <span>{saveState === 'saved' ? '已保存' : saveState === 'saving' ? '保存中…' : '未保存'}</span>
          </div>
        )}
        {isPersistedNoteId(editingNoteId) && (
          <>
            <button type="button" className="topbar-action" title="版本历史" onClick={() => setVersionsOpen(true)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={16} height={16}>
                <circle cx="12" cy="12" r="9" />
                <path d="M12 7v5l3 2" />
              </svg>
            </button>
            <button
              type="button"
              className="topbar-action"
              title="导出 Markdown"
              onClick={async () => {
                if (!isPersistedNoteId(editingNoteId)) return;
                try {
                  const res = await getApi().exportNote(editingNoteId);
                  addToast({ type: 'success', message: `已导出:${(res.data as { path: string }).path}` });
                } catch (err) {
                  addToast({ type: 'error', message: err instanceof Error ? err.message : '导出失败' });
                }
              }}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={16} height={16}>
                <path d="M12 3v12M7 10l5 5 5-5M4 21h16" />
              </svg>
            </button>
          </>
        )}
        <button type="button" className="topbar-action" title="回收站" onClick={() => setTrashOpen(true)}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={16} height={16}>
            <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6" />
          </svg>
        </button>
        {isPersistedNoteId(editingNoteId) && (
          <button type="button" className="topbar-action" title="删除笔记" onClick={() => setDeleteOpen(true)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={16} height={16}>
              <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6" />
            </svg>
          </button>
        )}
      </header>

      <aside className="notes-list-pane">
        <div className="notes-list-header">
          <h3>笔记</h3>
          <span className="badge" style={{ fontFamily: 'var(--font-mono)' }}>
            {filtered.length}
          </span>
        </div>
        <div className="notes-list-body">
          <NoteList
            notes={filtered}
            projectNames={projectNames}
            selectedId={selectedNoteId}
            onSelect={(n) => {
              void fetchNoteFull(n.id).then((full) => {
                startEditing(full.id, full.title, full.content);
                setNewProjectId(n.project_id);
                dirtyRef.current = false;
                setSaveState('saved');
              });
            }}
          />
        </div>
      </aside>

      {view === 'list-only' && (
        <main className="notes-grid-view">
          <div className="row between mb-md">
            <div>
              <h2 className="h2" style={{ margin: 0 }}>
                所有笔记
              </h2>
              <p className="muted small mt-sm">
                {filtered.length} 篇笔记 · 跨 {projectCount} 个项目
              </p>
            </div>
            <button type="button" className="btn btn-primary" onClick={handleNew}>
              新建笔记
            </button>
          </div>
          <div className="notes-grid">
            {filtered.map((n) => (
              <button
                key={n.id}
                type="button"
                className="note-grid-card"
                onClick={() => {
                  startEditing(n.id, n.title, n.content);
                  setNewProjectId(n.project_id);
                  setView('split');
                }}
              >
                <span className="project-tag" style={{ background: 'var(--brand-50)', color: 'var(--brand-700)' }}>
                  {projectNames.get(n.project_id) ?? n.project_id}
                </span>
                <h4>{n.title}</h4>
                <p className="snippet">{n.content.slice(0, 120)}</p>
              </button>
            ))}
          </div>
        </main>
      )}

      <section className="edit-pane">
        {editingNoteId ? (
          <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
            {editingNoteId === 'new' && (
              <select
                className="input"
                value={newProjectId}
                onChange={(e) => {
                  setNewProjectId(e.target.value);
                }}
                style={{ margin: '12px 24px 0', maxWidth: 320 }}
              >
                <option value="">选择项目</option>
                {(projectsData?.items ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            )}
            <NoteEditor
              variant="notes"
              onSave={() => void handleSave()}
              saving={updateNote.isPending || createNote.isPending}
            />
          </div>
        ) : (
          <div className="empty-notes">
            <div className="empty-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={32} height={32}>
                <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                <path d="M14 2v6h6M8 13h8M8 17h5" />
              </svg>
            </div>
            <h3>选择一篇笔记开始</h3>
            <p>从左侧列表选择，或创建新笔记</p>
            <button type="button" className="btn btn-primary" onClick={handleNew}>
              新建笔记
            </button>
          </div>
        )}
      </section>

      <section className="preview-pane">
        <div className="preview-toolbar">
          <span className="live-dot" />
          <span>实时预览</span>
          <span style={{ marginLeft: 8, fontWeight: 400, color: 'var(--text-500)' }}>
            Markdown · 实时渲染
          </span>
        </div>
        <div className="preview-content markdown">
          {editingNoteId ? (
            <>
              {editorTitle && <h1 className="preview-h1">{editorTitle}</h1>}
              <MarkdownRenderer content={editorContent} />
              {isPersistedNoteId(editingNoteId) && (
                <>
                  <TocPanel noteId={editingNoteId} />
                  <BacklinkPanel noteId={editingNoteId} />
                </>
              )}
            </>
          ) : (
            <p className="muted">预览区</p>
          )}
        </div>
      </section>

      <div className="status-bar">
        <div className="left">
          <span>{notes.length} 笔记</span>
          <span>·</span>
          <span>{editingNoteId ? editorTitle || '无标题' : '未选择'}</span>
        </div>
        <div className="right">
          <span>Markdown · 实时预览</span>
          <span>
            <kbd>⌘</kbd>+<kbd>S</kbd> 保存
          </span>
        </div>
      </div>

      <VersionDrawer noteId={editingNoteId} open={versionsOpen} onClose={() => setVersionsOpen(false)} />
      <TrashPanel
        open={trashOpen}
        onClose={() => setTrashOpen(false)}
        onOpenNote={(id) => {
          setTrashOpen(false);
          void fetchNoteFull(id).then((full) => {
            startEditing(full.id, full.title, full.content);
            setSaveState('saved');
          });
        }}
      />
      <ConfirmDialog
        open={deleteOpen}
        title="删除笔记"
        message="确定删除此笔记？"
        danger
        onConfirm={() => {
          if (isPersistedNoteId(editingNoteId)) {
            void deleteNote.mutateAsync(editingNoteId);
          }
          setDeleteOpen(false);
        }}
        onCancel={() => setDeleteOpen(false)}
      />
    </div>
  );
}
