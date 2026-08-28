/** Markdown 编辑器(CodeMirror 6 封装):语法高亮/选区包裹工具栏/贴图即传。
 *
 * 依赖注入而非包装库(@uiw):主题经 EditorView.theme 读 CSS 变量,
 * 亮暗切换随 data-theme 即时生效;字号读 --notes-md-size,无需重载。
 * 粘贴/拖拽 image/* → uploadFile → notes.add_asset → 光标处插 attachment:// 引用。
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { EditorState } from '@codemirror/state';
import { EditorView, highlightActiveLine, keymap, lineNumbers } from '@codemirror/view';
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands';
import { markdown, markdownLanguage } from '@codemirror/lang-markdown';
import { languages } from '@codemirror/language-data';
import { useNoteStore } from '@/stores/noteStore';
import { useUIStore } from '@/stores/uiStore';
import { applyLinePrefix } from './noteUtils';

export interface NoteEditorHandle {
  scrollDom: HTMLElement;
  goToLine: (line: number) => void;
}

interface NoteEditorProps {
  onSave: () => void;
  saving?: boolean;
  onReady?: (api: NoteEditorHandle | null) => void;
  /** 格式栏挂到分栏上方,左右正文从同一高度开始 */
  formatBarHost?: HTMLElement | null;
}

/** 编辑器主题:字号走 CSS 变量,亮暗切换零重载。 */
const markdownTheme = EditorView.theme({
  '&': {
    color: 'var(--text-1)',
    backgroundColor: 'transparent',
    fontSize: 'var(--notes-md-size, 15px)',
    height: '100%',
  },
  '.cm-content': {
    caretColor: 'var(--accent, #0a84ff)',
    fontFamily: 'var(--font-mono, ui-monospace, monospace)',
    lineHeight: '1.7',
    padding: '8px 16px 32px 4px',
    maxWidth: 'none',
  },
  '.cm-scroller': {
    overflow: 'auto',
    fontFamily: 'inherit',
  },
  '.cm-cursor, .cm-dropCursor': { borderLeftColor: 'var(--accent, #0a84ff)' },
  '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection':
    { backgroundColor: 'rgba(10, 132, 255, 0.18)' },
  '.cm-activeLine': { backgroundColor: 'rgba(120, 120, 128, 0.08)' },
  '.cm-gutters': {
    backgroundColor: 'transparent',
    color: 'var(--text-3)',
    border: 'none',
  },
}, { dark: false });

function wrapSelection(view: EditorView | null, before: string, after = before) {
  if (!view) return;
  const { state, dispatch } = view;
  const { from, to } = state.selection.main;
  const selected = state.sliceDoc(from, to);
  dispatch(state.replaceSelection(before + selected + after));
  const cursor = selected ? from + before.length + selected.length : from + before.length;
  dispatch({ selection: { anchor: cursor }, scrollIntoView: true });
  view.focus();
}

function toggleLinePrefix(view: EditorView | null, prefix: string) {
  if (!view) return;
  const { state, dispatch } = view;
  const { from, to } = state.selection.main;
  const startLine = state.doc.lineAt(from);
  const endLine = state.doc.lineAt(to);
  const changes: { from: number; to: number; insert: string }[] = [];
  for (let n = startLine.number; n <= endLine.number; n += 1) {
    const line = state.doc.line(n);
    changes.push({ from: line.from, to: line.to, insert: applyLinePrefix(line.text, prefix) });
  }
  dispatch({ changes, selection: { anchor: startLine.from } });
  view.focus();
}

function goToLine(view: EditorView, line: number) {
  const doc = view.state.doc;
  const n = Math.min(Math.max(1, line), doc.lines);
  const pos = doc.line(n).from;
  view.dispatch({ selection: { anchor: pos }, scrollIntoView: true });
  view.focus();
}

function Ico({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  );
}

export function NoteEditor({ onSave, saving, onReady, formatBarHost }: NoteEditorProps) {
  const title = useNoteStore((s) => s.editorTitle);
  const content = useNoteStore((s) => s.editorContent);
  const setTitle = useNoteStore((s) => s.setEditorTitle);
  const setContent = useNoteStore((s) => s.setEditorContent);
  const addToast = useUIStore((s) => s.addToast);
  const viewRef = useRef<EditorView | null>(null);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [uploading, setUploading] = useState(false);
  const [tip, setTip] = useState<{ text: string; x: number; y: number } | null>(null);
  const onSaveRef = useRef(onSave);
  onSaveRef.current = onSave;
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;

  const wordCount = useMemo(() => content.replace(/\s/g, '').length, [content]);

  const showTip = (text: string, el: HTMLElement) => {
    const r = el.getBoundingClientRect();
    setTip({ text, x: r.left + r.width / 2, y: r.bottom });
  };

  const uploadImages = async (files: File[]) => {
    const view = viewRef.current;
    setUploading(true);
    try {
      for (const file of files) {
        const { uploadFile } = await import('@/bridge/client');
        const { file_path, filename } = await uploadFile(file);
        const res = await (await import('@/api/client')).getApi().addAsset(file_path, filename);
        const payload = res && typeof res === 'object' && 'data' in res
          ? (res as { data: { markdown?: string; url?: string } }).data
          : null;
        const md = payload?.markdown ?? (payload?.url ? `![](${payload.url})` : `![](${String(res)})`);
        if (view) {
          view.dispatch(view.state.replaceSelection(`\n${md}\n`));
          view.focus();
        } else {
          setContent(content + md);
        }
      }
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : '图片上传失败',
      });
    } finally {
      setUploading(false);
    }
  };

  useEffect(() => {
    if (!hostRef.current) return;
    const state = EditorState.create({
      doc: content,
      extensions: [
        history(),
        lineNumbers(),
        highlightActiveLine(),
        keymap.of([...defaultKeymap, ...historyKeymap, indentWithTab]),
        markdown({ base: markdownLanguage, codeLanguages: languages }),
        markdownTheme,
        EditorView.lineWrapping,
        EditorView.updateListener.of((update) => {
          if (update.docChanged) setContent(update.state.doc.toString());
        }),
        keymap.of([
          {
            key: 'Mod-s',
            preventDefault: true,
            run: () => {
              onSaveRef.current();
              return true;
            },
          },
          {
            key: 'Mod-b',
            preventDefault: true,
            run: (view) => {
              wrapSelection(view, '**');
              return true;
            },
          },
          {
            key: 'Mod-i',
            preventDefault: true,
            run: (view) => {
              wrapSelection(view, '*');
              return true;
            },
          },
        ]),
        EditorView.domEventHandlers({
          paste: (event) => {
            const files = Array.from(event.clipboardData?.files ?? []).filter((f) =>
              f.type.startsWith('image/'));
            if (files.length === 0) return false;
            event.preventDefault();
            void uploadImages(files);
            return true;
          },
          drop: (event) => {
            const files = Array.from(event.dataTransfer?.files ?? []).filter((f) =>
              f.type.startsWith('image/'));
            if (files.length === 0) return false;
            event.preventDefault();
            void uploadImages(files);
            return true;
          },
        }),
      ],
    });
    const view = new EditorView({ state, parent: hostRef.current });
    viewRef.current = view;
    onReadyRef.current?.({
      scrollDom: view.scrollDOM,
      goToLine: (line) => goToLine(view, line),
    });
    return () => {
      onReadyRef.current?.(null);
      view.destroy();
      viewRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (current !== content) {
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: content } });
    }
  }, [content]);

  const btn = (
    label: string,
    onClick: () => void,
    child: ReactNode,
    extra = '',
  ) => (
    <button
      type="button"
      className={`edit-toolbar-btn${extra ? ` ${extra}` : ''}`}
      aria-label={label}
      onMouseEnter={(e) => showTip(label, e.currentTarget)}
      onMouseLeave={() => setTip(null)}
      onClick={onClick}
    >
      {child}
    </button>
  );

  const toolbar = (
    <div className="edit-toolbar">
      {btn('加粗', () => wrapSelection(viewRef.current, '**'), <strong>B</strong>, 'bold')}
      {btn('斜体', () => wrapSelection(viewRef.current, '*'), <em>I</em>)}
      {btn('行内代码', () => wrapSelection(viewRef.current, '`'), <Ico d="M16 18l6-6-6-6M8 6l-6 6 6 6" />, 'code')}
      {btn('链接', () => wrapSelection(viewRef.current, '[', '](https://)'), (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
          <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" />
          <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" />
        </svg>
      ))}
      <div className="edit-toolbar-divider" />
      {btn('标题', () => toggleLinePrefix(viewRef.current, '## '), 'H')}
      {btn('引用', () => toggleLinePrefix(viewRef.current, '> '), (
        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <path d="M7 17h4l2-4V7H5v6h4zm8 0h4l2-4V7h-8v6h4z" />
        </svg>
      ))}
      {btn('无序列表', () => toggleLinePrefix(viewRef.current, '- '), <Ico d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />)}
      {btn('任务列表', () => toggleLinePrefix(viewRef.current, '- [ ] '), <Ico d="M9 11l3 3L22 4M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />)}
      <div className="edit-toolbar-divider" />
      {btn('代码块', () => wrapSelection(viewRef.current, '\n```\n', '\n```\n'), (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
          <polyline points="16 18 22 12 16 6" />
          <polyline points="8 6 2 12 8 18" />
        </svg>
      ))}
      {btn('表格', () => wrapSelection(viewRef.current, '\n| 列A | 列B |\n| --- | --- |\n|  |  |\n', ''), (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <path d="M3 9h18M3 15h18M9 3v18" />
        </svg>
      ))}
      {btn(uploading ? '上传中…' : '插入图片', () => {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/png,image/jpeg,image/gif,image/webp,image/svg+xml';
        input.onchange = () => {
          if (input.files) void uploadImages(Array.from(input.files));
        };
        input.click();
      }, (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <path d="M21 15l-5-5L5 21" />
        </svg>
      ))}
      <div className="edit-toolbar-divider" />
      <button
        type="button"
        className="btn btn-primary btn-sm"
        data-testid="save-note-btn"
        style={{ marginLeft: 'auto' }}
        onClick={onSave}
        disabled={saving}
      >
        {saving ? '保存中…' : '保存'}
      </button>
      <span className="muted" style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>
        {wordCount} 字
      </span>
    </div>
  );

  return (
    <div className="note-editor">
      {formatBarHost ? createPortal(toolbar, formatBarHost) : formatBarHost === undefined ? toolbar : null}
      {tip
        ? createPortal(
            <div className="notes-toolbar-tip" style={{ left: tip.x, top: tip.y }} role="tooltip">
              {tip.text}
            </div>,
            document.body,
          )
        : null}
      <input
        className="edit-title-input"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="无标题笔记"
      />
      <div className="edit-content-area edit-content-area--cm" ref={hostRef} data-testid="note-editor-cm" />
    </div>
  );
}
