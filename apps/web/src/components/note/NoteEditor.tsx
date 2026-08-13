import { useMemo, useRef, type KeyboardEvent } from 'react';
import { useNoteStore } from '@/stores/noteStore';

interface NoteEditorProps {
  onSave: () => void;
  saving?: boolean;
  variant?: 'default' | 'notes';
}

function insertAtCursor(
  textarea: HTMLTextAreaElement | null,
  text: string,
  content: string,
  setContent: (v: string) => void
) {
  if (!textarea) {
    setContent(content + text);
    return;
  }
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  const next = content.slice(0, start) + text + content.slice(end);
  setContent(next);
}

export function NoteEditor({ onSave, saving, variant = 'default' }: NoteEditorProps) {
  const title = useNoteStore((s) => s.editorTitle);
  const content = useNoteStore((s) => s.editorContent);
  const setTitle = useNoteStore((s) => s.setEditorTitle);
  const setContent = useNoteStore((s) => s.setEditorContent);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const wordCount = useMemo(() => content.replace(/\s/g, '').length, [content]);

  const handleInsert = (snippet: string) => {
    insertAtCursor(textareaRef.current, snippet, content, setContent);
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 's') {
      e.preventDefault();
      onSave();
    }
    if ((e.metaKey || e.ctrlKey) && e.key === 'b') {
      e.preventDefault();
      handleInsert('**粗体**');
    }
  };

  if (variant === 'notes') {
    return (
      <>
        <div className="edit-toolbar">
          <button type="button" className="edit-toolbar-btn bold" title="加粗" onClick={() => handleInsert('**粗体**')}>
            <strong>B</strong>
          </button>
          <button type="button" className="edit-toolbar-btn" title="斜体" onClick={() => handleInsert('*斜体*')}>
            <em>I</em>
          </button>
          <div className="edit-toolbar-divider" />
          <button type="button" className="edit-toolbar-btn" title="标题" onClick={() => handleInsert('## 标题')}>
            H
          </button>
          <button type="button" className="edit-toolbar-btn code" title="行内代码" onClick={() => handleInsert('`code`')}>
            {'</>'}
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
        <input
          className="edit-title-input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="无标题笔记"
        />
        <textarea
          ref={textareaRef}
          className="edit-content-area"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="开始用 Markdown 记录..."
          spellCheck={false}
        />
      </>
    );
  }

  return (
    <div className="note-editor">
      <div className="note-editor__toolbar">
        <button type="button" className="btn btn-primary btn-sm" data-testid="save-note-btn" onClick={onSave} disabled={saving}>
          {saving ? '保存中…' : '保存'}
        </button>
      </div>
      <input
        className="input note-editor__title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="笔记标题"
      />
      <textarea
        className="input textarea note-editor__body"
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="Markdown 内容…"
      />
    </div>
  );
}
