import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  fetchNoteFull,
  useAllNotes,
  useCreateNote,
  useDeleteNote,
  useLinkNote,
  usePatchNoteMeta,
  useUpdateNote,
} from '@/hooks/useNotes';
import { useProjects } from '@/hooks/useProjects';
import { useNoteStore } from '@/stores/noteStore';
import { useNotesUiStore } from '@/stores/notesUiStore';
import { useUIStore } from '@/stores/uiStore';
import { getApi } from '@/api/client';
import { consumeAgentSSEStream } from '@/utils/agentSSEStream';
import { routes } from '@/utils/routes';
import type { Note } from '@/api/types';
import { NoteEditor, type NoteEditorHandle } from './NoteEditor';
import { NoteIndex } from './NoteIndex';
import { NotePreview } from './NotePreview';
import { NotesWorkspaceBar } from './NotesWorkspaceBar';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { TrashPanel, VersionDrawer } from './NoteFeatures';
import {
  bumpNotesFont,
  commitNotesLayout,
  commitNotesListState,
  commitNotesMode,
  commitNotesSyncScroll,
} from './notesView';
import {
  isPersistedNoteId,
  noteSnippet,
  noteSourceId,
  parseSplitRatio,
  syncScrollRatio,
} from './noteUtils';

function noteQueryId(params: URLSearchParams): string | null {
  return params.get('note') ?? params.get('open');
}

export function NotesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const noteParam = noteQueryId(searchParams);
  const isWorkspace = Boolean(noteParam);
  const listState = useNotesUiStore((s) => s.listState);
  const layout = useNotesUiStore((s) => s.layout);
  const mode = useNotesUiStore((s) => s.mode);
  const fontSize = useNotesUiStore((s) => s.fontSize);
  const syncScroll = useNotesUiStore((s) => s.syncScroll);
  const splitRatio = useNotesUiStore((s) => s.splitRatio);
  const setSplitRatio = useNotesUiStore((s) => s.setSplitRatio);
  const { data: notes = [], isLoading } = useAllNotes(listState);
  const { data: projectsData } = useProjects();
  const searchQuery = useNoteStore((s) => s.searchQuery);
  const setSearchQuery = useNoteStore((s) => s.setSearchQuery);
  const editorContent = useNoteStore((s) => s.editorContent);
  const editorTitle = useNoteStore((s) => s.editorTitle);
  const startEditing = useNoteStore((s) => s.startEditing);
  const setEditorContent = useNoteStore((s) => s.setEditorContent);
  const setEditorTitle = useNoteStore((s) => s.setEditorTitle);
  const editingNoteId = useNoteStore((s) => s.editingNoteId);
  const createNote = useCreateNote();
  const updateNote = useUpdateNote();
  const deleteNote = useDeleteNote();
  const linkNote = useLinkNote();
  const patchMeta = usePatchNoteMeta();
  const addToast = useUIStore((s) => s.addToast);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [newProjectId, setNewProjectId] = useState(() => searchParams.get('project') ?? '');
  const [projectFilter, setProjectFilter] = useState(() => searchParams.get('project') ?? '');
  const [trashOpen, setTrashOpen] = useState(false);
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [saveState, setSaveState] = useState<'saved' | 'unsaved' | 'saving'>('saved');
  const dirtyRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastPersistedRef = useRef<{ id: string; title: string; content: string } | null>(null);
  const [editorApi, setEditorApi] = useState<NoteEditorHandle | null>(null);
  const [previewEl, setPreviewEl] = useState<HTMLDivElement | null>(null);
  const [scribeStreaming, setScribeStreaming] = useState(false);
  const [opening, setOpening] = useState(false);
  const [meta, setMeta] = useState<{ pinned: boolean; archived: boolean }>({ pinned: false, archived: false });
  const [formatBarHost, setFormatBarHost] = useState<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const noteSeqRef = useRef(0);

  const flush = useCallback(async () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    if (!dirtyRef.current) return;
    const id = useNoteStore.getState().editingNoteId;
    const t = useNoteStore.getState().editorTitle;
    const c = useNoteStore.getState().editorContent;
    if (!t.trim()) return;
    if (isPersistedNoteId(id)) {
      if (
        lastPersistedRef.current?.id === id &&
        lastPersistedRef.current?.title === t &&
        lastPersistedRef.current?.content === c
      ) {
        dirtyRef.current = false;
        setSaveState('saved');
        return;
      }
      setSaveState('saving');
      try {
        await updateNote.mutateAsync({ id, title: t, content: c });
        lastPersistedRef.current = { id, title: t, content: c };
        dirtyRef.current = false;
        setSaveState('saved');
      } catch (err) {
        setSaveState('unsaved');
        addToast({ type: 'error', message: err instanceof Error ? err.message : '保存失败' });
      }
    } else {
      setSaveState('saving');
      try {
        const created = await createNote.mutateAsync({
          projectId: newProjectId || '',
          title: t,
          content: c,
        });
        lastPersistedRef.current = {
          id: created.id,
          title: created.title ?? t,
          content: created.content ?? c,
        };
        dirtyRef.current = false;
        setSaveState('saved');
        setSearchParams(
          (prev) => {
            const next = new URLSearchParams(prev);
            next.set('note', created.id);
            next.delete('open');
            return next;
          },
          { replace: true },
        );
      } catch (err) {
        setSaveState('unsaved');
        addToast({ type: 'error', message: err instanceof Error ? err.message : '保存失败' });
      }
    }
  }, [updateNote, createNote, newProjectId, addToast, setSearchParams]);

  const markDirty = useCallback(() => {
    dirtyRef.current = true;
    setSaveState('unsaved');
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => void flush(), 5000);
  }, [flush]);

  const loadedFor = useRef<string | null>(null);
  useEffect(() => {
    if (loadedFor.current !== editingNoteId) {
      loadedFor.current = editingNoteId;
      return;
    }
    const last = lastPersistedRef.current;
    if (
      isPersistedNoteId(editingNoteId) &&
      last &&
      last.id === editingNoteId &&
      last.title === editorTitle &&
      last.content === editorContent
    ) {
      return;
    }
    markDirty();
  }, [editorContent, editorTitle, editingNoteId, markDirty]);

  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!dirtyRef.current) return;
      const id = useNoteStore.getState().editingNoteId;
      const t = useNoteStore.getState().editorTitle;
      const c = useNoteStore.getState().editorContent;
      if (isPersistedNoteId(id) && t.trim()) {
        const blob = new Blob(
          [JSON.stringify({ note_id: id, title: t, content: c })],
          { type: 'application/json' },
        );
        navigator.sendBeacon('/api/notes/capabilities/update_note', blob);
      }
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', onBeforeUnload);
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const flushRef = useRef(flush);
  flushRef.current = flush;

  useEffect(() => {
    const noteId = noteQueryId(searchParams);
    let cancelled = false;

    const run = async () => {
      if (!noteId) {
        await flushRef.current();
        if (cancelled) return;
        const still = noteQueryId(new URLSearchParams(window.location.search));
        if (!still) useNoteStore.getState().stopEditing();
        return;
      }
      if (noteId === 'new') {
        if (useNoteStore.getState().editingNoteId !== 'new') {
          await flushRef.current();
          if (cancelled) return;
          startEditing('new', '新笔记', '');
          setNewProjectId(searchParams.get('project') || '');
          lastPersistedRef.current = null;
          dirtyRef.current = false;
          setSaveState('unsaved');
          setMeta({ pinned: false, archived: false });
        }
        return;
      }
      if (useNoteStore.getState().editingNoteId === noteId) return;
      await flushRef.current();
      if (cancelled) return;
      const seq = ++noteSeqRef.current;
      setOpening(true);
      try {
        const full = await fetchNoteFull(noteId);
        if (cancelled || seq !== noteSeqRef.current) return;
        startEditing(full.id, full.title, full.content);
        setNewProjectId(noteSourceId(full));
        lastPersistedRef.current = { id: full.id, title: full.title, content: full.content };
        dirtyRef.current = false;
        setSaveState('saved');
        setMeta({ pinned: Boolean(full.pinned), archived: Boolean(full.archived) });
      } catch (err) {
        addToast({ type: 'error', message: err instanceof Error ? err.message : '打开笔记失败' });
        if (!cancelled) navigate(routes.notes, { replace: true });
      } finally {
        if (seq === noteSeqRef.current) setOpening(false);
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [searchParams, startEditing, addToast, navigate]);

  const projectNames = useMemo(() => {
    const m = new Map<string, string>();
    for (const p of projectsData?.items ?? []) {
      m.set(p.id, p.name);
    }
    return m;
  }, [projectsData]);

  const projectOptions = useMemo(
    () => (projectsData?.items ?? []).map((p) => ({ value: p.id, label: p.name })),
    [projectsData],
  );

  const filtered = useMemo(() => {
    const q = searchQuery.toLowerCase();
    return notes.filter((n) => {
      const src = noteSourceId(n);
      if (projectFilter && src !== projectFilter) return false;
      if (!q) return true;
      return (
        n.title.toLowerCase().includes(q) ||
        noteSnippet(n).toLowerCase().includes(q) ||
        (projectNames.get(src) ?? '').toLowerCase().includes(q)
      );
    });
  }, [notes, searchQuery, projectNames, projectFilter]);

  const goIndex = useCallback(async () => {
    await flush();
    navigate(routes.notes);
  }, [flush, navigate]);

  const openNote = useCallback(
    async (n: Note) => {
      await flush();
      navigate(routes.note(n.id));
    },
    [flush, navigate],
  );

  const handleNew = async () => {
    await flush();
    const project = searchParams.get('project') || projectFilter || '';
    if (noteQueryId(searchParams) === 'new') {
      startEditing('new', '新笔记', '');
      setNewProjectId(project);
      lastPersistedRef.current = null;
      dirtyRef.current = false;
      setSaveState('unsaved');
      setMeta({ pinned: false, archived: false });
      return;
    }
    navigate(routes.note('new', project || undefined));
  };

  const handleProjectChange = async (value: string) => {
    setNewProjectId(value);
    if (!isPersistedNoteId(editingNoteId)) return;
    try {
      await linkNote.mutateAsync({ id: editingNoteId, sourceId: value || null });
    } catch (err) {
      addToast({ type: 'error', message: err instanceof Error ? err.message : '关联项目失败' });
    }
  };

  const handlePin = async (note: Note, pinned: boolean) => {
    try {
      await patchMeta.mutateAsync({ id: note.id, pinned });
      if (note.id === editingNoteId) setMeta((m) => ({ ...m, pinned }));
    } catch (err) {
      addToast({ type: 'error', message: err instanceof Error ? err.message : '置顶失败' });
    }
  };

  const togglePinCurrent = () => {
    if (!isPersistedNoteId(editingNoteId)) return;
    void handlePin({ id: editingNoteId } as Note, !meta.pinned);
  };

  const toggleArchiveCurrent = async () => {
    if (!isPersistedNoteId(editingNoteId)) return;
    const archived = !meta.archived;
    try {
      await patchMeta.mutateAsync({ id: editingNoteId, archived });
      setMeta((m) => ({ ...m, archived }));
      if (archived) {
        await flush();
        navigate(routes.notes);
      }
    } catch (err) {
      addToast({ type: 'error', message: err instanceof Error ? err.message : '归档失败' });
    }
  };

  const runScribe = async () => {
    const projectId =
      newProjectId ||
      noteSourceId(notes.find((n) => n.id === editingNoteId) ?? {}) ||
      searchParams.get('project') ||
      projectsData?.items[0]?.id;
    if (!projectId) {
      addToast({ type: 'warning', message: '请先选择关联项目' });
      return;
    }
    if (!editingNoteId) {
      startEditing('new', 'Miyai 笔记草稿', '');
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
        addToast({ type: 'success', message: 'Miyai 已生成笔记草稿' });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '笔记生成失败';
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
    dirtyRef.current = true;
    await flush();
  };

  const onSplitPointerDown = (e: ReactPointerEvent<HTMLButtonElement>) => {
    e.preventDefault();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const onMove = (ev: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      if (rect.width < 80) return;
      setSplitRatio(parseSplitRatio(String((ev.clientX - rect.left) / rect.width)));
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  useEffect(() => {
    if (!isWorkspace) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === '=' || e.key === '+' || e.key === '-')) {
        e.preventDefault();
        bumpNotesFont(e.key === '-' ? -1 : 1);
        return;
      }
      if (e.key !== 'Escape') return;
      if (deleteOpen || versionsOpen || trashOpen) return;
      if (document.querySelector('.glass-select.is-open')) return;
      e.preventDefault();
      void goIndex();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isWorkspace, deleteOpen, versionsOpen, trashOpen, goIndex]);

  useEffect(() => {
    if (mode !== 'split' || !syncScroll) return;
    const a = editorApi?.scrollDom;
    const b = previewEl;
    if (!a || !b) return;
    let lock = false;
    const bind = (from: HTMLElement, to: HTMLElement) => () => {
      if (lock) return;
      lock = true;
      syncScrollRatio(from, to);
      requestAnimationFrame(() => {
        lock = false;
      });
    };
    const onA = bind(a, b);
    const onB = bind(b, a);
    a.addEventListener('scroll', onA, { passive: true });
    b.addEventListener('scroll', onB, { passive: true });
    return () => {
      a.removeEventListener('scroll', onA);
      b.removeEventListener('scroll', onB);
    };
  }, [mode, syncScroll, editorApi, previewEl]);

  const showEdit = mode === 'edit' || mode === 'split';
  const showPreview = mode === 'preview' || mode === 'split';
  const persisted = isPersistedNoteId(editingNoteId);

  if (!isWorkspace && isLoading && notes.length === 0) return <LoadingSpinner fullScreen />;

  const drawers = (
    <>
      <VersionDrawer
        noteId={persisted ? editingNoteId : ''}
        open={versionsOpen && persisted}
        onClose={() => setVersionsOpen(false)}
      />
      <TrashPanel
        open={trashOpen}
        onClose={() => setTrashOpen(false)}
        onOpenNote={async (id) => {
          setTrashOpen(false);
          await flush();
          navigate(routes.note(id));
        }}
      />
      <ConfirmDialog
        open={deleteOpen}
        title="删除笔记"
        message="确定将此笔记移入回收站?之后可在回收站恢复。"
        confirmLabel="移入回收站"
        danger
        onConfirm={() => {
          if (persisted) {
            void deleteNote.mutateAsync(editingNoteId).then(
              () => {
                addToast({ type: 'success', message: '已移入回收站' });
                navigate(routes.notes);
              },
              (err: unknown) => addToast({ type: 'error', message: err instanceof Error ? err.message : '删除失败' }),
            );
          }
          setDeleteOpen(false);
        }}
        onCancel={() => setDeleteOpen(false)}
      />
    </>
  );

  if (!isWorkspace) {
    return (
      <>
        <NoteIndex
          notes={filtered}
          empty={notes.length === 0}
          layout={layout}
          listState={listState}
          onLayoutChange={commitNotesLayout}
          onListStateChange={commitNotesListState}
          searchQuery={searchQuery}
          onSearch={setSearchQuery}
          projectFilter={projectFilter}
          onProjectFilter={setProjectFilter}
          projectOptions={projectOptions}
          projectNames={projectNames}
          onOpen={(n) => void openNote(n)}
          onNew={() => void handleNew()}
          onTrash={() => setTrashOpen(true)}
          onPin={(n, pinned) => void handlePin(n, pinned)}
        />
        {drawers}
      </>
    );
  }

  const workspaceReady = noteParam === 'new' || editingNoteId === noteParam;

  return (
    <div
      className="notes-shell notes-workspace-page"
      style={{ ['--notes-md-size' as string]: `${fontSize}px` }}
    >
      <NotesWorkspaceBar
        mode={mode}
        fontSize={fontSize}
        saveState={saveState}
        persisted={persisted}
        pinned={meta.pinned}
        archived={meta.archived}
        projectId={newProjectId}
        projectOptions={projectOptions}
        scribeStreaming={scribeStreaming}
        syncScroll={syncScroll}
        onBack={() => void goIndex()}
        onNew={() => void handleNew()}
        onMode={commitNotesMode}
        onBumpFont={bumpNotesFont}
        onProject={(v) => void handleProjectChange(v)}
        onTogglePin={togglePinCurrent}
        onToggleArchive={() => void toggleArchiveCurrent()}
        onToggleSync={() => commitNotesSyncScroll(!syncScroll)}
        onScribe={() => void runScribe()}
        onVersions={() => setVersionsOpen(true)}
        onExport={() => {
          if (!persisted) return;
          void getApi()
            .exportNote(editingNoteId)
            .then((res) => {
              addToast({ type: 'success', message: `已导出:${(res.data as { path: string }).path}` });
            })
            .catch((err: unknown) => {
              addToast({ type: 'error', message: err instanceof Error ? err.message : '导出失败' });
            });
        }}
        onDelete={() => setDeleteOpen(true)}
        onTrash={() => setTrashOpen(true)}
      />

      {showEdit && !(opening && !workspaceReady) ? (
        <div className="notes-format-bar" ref={setFormatBarHost} data-testid="notes-format-bar" />
      ) : null}

      <div
        ref={canvasRef}
        className={`notes-workspace notes-canvas is-${mode}`}
        style={mode === 'split' ? { ['--notes-edit-pct' as string]: `${Math.round(splitRatio * 1000) / 10}%` } : undefined}
      >
        {opening && !workspaceReady ? (
          <LoadingSpinner label="打开笔记…" />
        ) : (
          <>
            {showEdit && (
              <section className="edit-pane">
                <div className="note-editor-wrap">
                  <NoteEditor
                    onSave={() => void handleSave()}
                    saving={updateNote.isPending || createNote.isPending}
                    onReady={setEditorApi}
                    formatBarHost={formatBarHost}
                  />
                </div>
              </section>
            )}
            {mode === 'split' && (
              <button
                type="button"
                className="notes-split-handle"
                aria-label="拖动调整左右栏宽度"
                onPointerDown={onSplitPointerDown}
              />
            )}
            {showPreview && (
              <section className="preview-pane">
                <NotePreview
                  title={editorTitle}
                  content={editorContent}
                  noteId={persisted ? editingNoteId : null}
                  inspectable={mode === 'preview'}
                  onScrollEl={setPreviewEl}
                  onJumpToLine={mode === 'split' ? (line) => editorApi?.goToLine(line) : undefined}
                />
              </section>
            )}
          </>
        )}
      </div>
      {drawers}
    </div>
  );
}
