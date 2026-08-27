/** Markdown 编辑器:textarea + 预览分屏;间隔自动保存(autosave_s=0 关),切篇/卸载 flush。 */

import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { useNotesStore } from './notesStore';

export function NoteEditor() {
  const current = useNotesStore((s) => s.current);
  const autosaveS = useNotesStore((s) => s.autosaveS);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  /** 最新草稿与脏标记(ref 供定时器/卸载 flush 读取,避免闭包旧值) */
  const draftRef = useRef({ title: '', content: '', dirty: false });
  const noteIdRef = useRef<string | null>(null);

  const flush = async () => {
    const id = noteIdRef.current;
    const d = draftRef.current;
    if (!id || !d.dirty) return;
    setSaving(true);
    try {
      await useNotesStore.getState().save(id, { title: d.title, content: d.content });
      draftRef.current.dirty = false;
      setSavedAt(new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }));
    } finally {
      setSaving(false);
    }
  };

  // 切篇:先 flush 旧篇草稿,再载入新篇
  useEffect(() => {
    if (current?.id === noteIdRef.current) return;
    const stale = { id: noteIdRef.current, draft: draftRef.current };
    noteIdRef.current = current?.id ?? null;
    setTitle(current?.title ?? '');
    setContent(current?.content ?? '');
    draftRef.current = { title: current?.title ?? '', content: current?.content ?? '', dirty: false };
    if (stale.id && stale.draft.dirty) {
      void useNotesStore.getState().save(stale.id, {
        title: stale.draft.title,
        content: stale.draft.content,
      });
    }
  }, [current]);

  // 自动保存定时器(autosave_s=0 关闭)
  useEffect(() => {
    if (autosaveS <= 0) return;
    const timer = window.setInterval(() => {
      if (draftRef.current.dirty) void flush();
    }, autosaveS * 1000);
    return () => window.clearInterval(timer);
  }, [autosaveS]);

  // 卸载前 flush
  useEffect(
    () => () => {
      const d = draftRef.current;
      const id = noteIdRef.current;
      if (id && d.dirty) {
        void useNotesStore.getState().save(id, { title: d.title, content: d.content });
      }
    },
    [],
  );

  if (!current) {
    return (
      <div className="note-editor note-editor--empty muted">
        选择或新建一篇笔记开始编辑。
      </div>
    );
  }

  const dirty = draftRef.current.dirty;

  return (
    <div className="note-editor">
      <div className="note-editor__bar">
        <input
          className="setting-input note-editor__title"
          value={title}
          placeholder="标题"
          onChange={(e) => {
            setTitle(e.target.value);
            draftRef.current = { ...draftRef.current, title: e.target.value, dirty: true };
          }}
        />
        <span className="small muted note-editor__status">
          {saving ? '保存中…' : dirty ? '未保存' : savedAt ? `已保存 ${savedAt}` : '已保存'}
        </span>
      </div>
      <div className="note-editor__split">
        <textarea
          className="note-editor__textarea"
          value={content}
          placeholder="Markdown 正文…"
          onChange={(e) => {
            setContent(e.target.value);
            draftRef.current = { ...draftRef.current, content: e.target.value, dirty: true };
          }}
          onBlur={() => void flush()}
        />
        <div className="note-editor__preview chat-md">
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
            {content || '(空)'}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
