/** Markdown 编辑器(CodeMirror 6 封装):语法高亮/选区包裹工具栏/贴图即传。
 *
 * 依赖注入而非包装库(@uiw):主题经 EditorView.theme 读 CSS 变量,
 * 亮暗切换随 data-theme 即时生效;对外 API 与旧 textarea 版一致
 * (值走 noteStore,仅 NotesPage 使用)。
 * 粘贴/拖拽 image/* → uploadFile → notes.add_asset → 光标处插 attachment:// 引用。
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { EditorState } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands';
import { markdown, markdownLanguage } from '@codemirror/lang-markdown';
import { languages } from '@codemirror/language-data';
import { useNoteStore } from '@/stores/noteStore';
import { useUIStore } from '@/stores/uiStore';

interface NoteEditorProps {
  onSave: () => void;
  saving?: boolean;
}

/** 编辑器主题:全部读 CSS 变量,亮暗切换零重载。 */
const markdownTheme = EditorView.theme({
  '&': {
    color: 'var(--text-1)',
    backgroundColor: 'transparent',
    fontSize: '13.5px',
    height: '100%',
  },
  '.cm-content': {
    caretColor: 'var(--accent, #0a84ff)',
    fontFamily: 'var(--font-mono, ui-monospace, monospace)',
    lineHeight: '1.7',
    padding: '12px 0',
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

/** 选区包裹:有选区包两侧,无选区插入标记对并把光标落中间。 */
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

/** 行前缀切换(标题/引用/列表):对选区每行设置前缀。 */
function toggleLinePrefix(view: EditorView | null, prefix: string) {
  if (!view) return;
  const { state, dispatch } = view;
  const { from, to } = state.selection.main;
  const startLine = state.doc.lineAt(from);
  const endLine = state.doc.lineAt(to);
  const changes: { from: number; insert: string }[] = [];
  for (let n = startLine.number; n <= endLine.number; n += 1) {
    const line = state.doc.line(n);
    const stripped = line.text.replace(/^(#{1,6}\s|>\s?|[-*]\s|\d+\.\s)/, '');
    changes.push({ from: line.from, insert: prefix + stripped });
    if (line.text !== stripped && line.to >= to) break;
  }
  dispatch({ changes, selection: { anchor: startLine.from } });
  view.focus();
}

export function NoteEditor({ onSave, saving }: NoteEditorProps) {
  const title = useNoteStore((s) => s.editorTitle);
  const content = useNoteStore((s) => s.editorContent);
  const setTitle = useNoteStore((s) => s.setEditorTitle);
  const setContent = useNoteStore((s) => s.setEditorContent);
  const addToast = useUIStore((s) => s.addToast);
  const viewRef = useRef<EditorView | null>(null);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [uploading, setUploading] = useState(false);
  // onSave 走 keymap 闭包:用 ref 保证注册的 keymap 永远调到最新回调
  const onSaveRef = useRef(onSave);
  onSaveRef.current = onSave;

  const wordCount = useMemo(() => content.replace(/\s/g, '').length, [content]);

  // ---- 贴图上传:paste / drop 的 image/* → 上传 → 光标插引用 ----
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
    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 外部写入(切笔记/版本回退)同步进 CM;相等时跳过以打断 updateListener 环
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (current !== content) {
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: content } });
    }
  }, [content]);

  const toolbar = (
    <div className="edit-toolbar">
      <button type="button" className="edit-toolbar-btn bold" title="加粗 (⌘B)" onClick={() => wrapSelection(viewRef.current, '**')}>
        <strong>B</strong>
      </button>
      <button type="button" className="edit-toolbar-btn" title="斜体" onClick={() => wrapSelection(viewRef.current, '*')}>
        <em>I</em>
      </button>
      <button type="button" className="edit-toolbar-btn code" title="行内代码" onClick={() => wrapSelection(viewRef.current, '`')}>
        {'</>'}
      </button>
      <button type="button" className="edit-toolbar-btn" title="链接 (⌘K)" onClick={() => wrapSelection(viewRef.current, '[', '](https://)')}>
        🔗
      </button>
      <div className="edit-toolbar-divider" />
      <button type="button" className="edit-toolbar-btn" title="标题" onClick={() => toggleLinePrefix(viewRef.current, '## ')}>
        H
      </button>
      <button type="button" className="edit-toolbar-btn" title="引用" onClick={() => toggleLinePrefix(viewRef.current, '> ')}>
        ❝
      </button>
      <button type="button" className="edit-toolbar-btn" title="无序列表" onClick={() => toggleLinePrefix(viewRef.current, '- ')}>
        •
      </button>
      <button type="button" className="edit-toolbar-btn" title="任务列表" onClick={() => toggleLinePrefix(viewRef.current, '- [ ] ')}>
        ☑
      </button>
      <div className="edit-toolbar-divider" />
      <button type="button" className="edit-toolbar-btn" title="代码块" onClick={() => wrapSelection(viewRef.current, '\n```js\n', '\n```\n')}>
        {'{ }'}
      </button>
      <button type="button" className="edit-toolbar-btn" title="表格" onClick={() => wrapSelection(viewRef.current, '\n| 列A | 列B |\n| --- | --- |\n|  |  |\n', '')}>
        ⊞
      </button>
      <button
        type="button"
        className="edit-toolbar-btn"
        title={uploading ? '上传中…' : '插入图片(也可直接粘贴/拖拽)'}
        disabled={uploading}
        onClick={() => {
          const input = document.createElement('input');
          input.type = 'file';
          input.accept = 'image/png,image/jpeg,image/gif,image/webp,image/svg+xml';
          input.onchange = () => {
            if (input.files) void uploadImages(Array.from(input.files));
          };
          input.click();
        }}
      >
        {uploading ? '…' : '🖼'}
      </button>
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
    <>
      {toolbar}
      <input
        className="edit-title-input"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="无标题笔记"
      />
      <div className="edit-content-area edit-content-area--cm" ref={hostRef} data-testid="note-editor-cm" />
    </>
  );
}
