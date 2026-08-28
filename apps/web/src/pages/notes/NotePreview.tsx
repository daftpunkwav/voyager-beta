/** 笔记预览:整篇一次 Markdown 渲染(长文切视图/改字号不反复建解析器)。
 *  拖选词句交给讲解人格;纯预览可整篇切换源码。 */

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
import { personaDisplayName } from '@/constants/personas';
import { BacklinkPanel, TocPanel } from './NoteFeatures';
import { NOTE_PREVIEW_REMARK } from './noteMarks';
import { explainNotesQuote } from './notesView';
import { parseNotesQuote } from './noteUtils';

interface NotePreviewProps {
  title: string;
  content: string;
  noteId: string | null;
  /** 纯预览:可整篇查看 Markdown 源码 */
  inspectable?: boolean;
  onScrollEl?: (el: HTMLDivElement | null) => void;
}

interface ExplainChip {
  quote: string;
  x: number;
  y: number;
  below: boolean;
}

const EXPLAINER_NAME = personaDisplayName('explainer');

function selectionInside(root: HTMLElement): Range | null {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) return null;
  const node = sel.anchorNode;
  if (!node || !root.contains(node)) return null;
  if (sel.focusNode && !root.contains(sel.focusNode)) return null;
  return sel.getRangeAt(0);
}

function chipFromRange(range: Range): ExplainChip | null {
  const quote = parseNotesQuote(range.toString());
  if (!quote) return null;
  const rect = range.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) return null;
  const below = rect.top < 52;
  return {
    quote,
    x: rect.left + rect.width / 2,
    y: below ? rect.bottom + 8 : rect.top - 8,
    below,
  };
}

export const NotePreview = memo(function NotePreview({
  title,
  content,
  noteId,
  inspectable = false,
  onScrollEl,
}: NotePreviewProps) {
  const [showSource, setShowSource] = useState(false);
  const [chip, setChip] = useState<ExplainChip | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  const setRoot = useCallback(
    (el: HTMLDivElement | null) => {
      rootRef.current = el;
      onScrollEl?.(el);
    },
    [onScrollEl],
  );

  const syncChip = useCallback(() => {
    const root = rootRef.current;
    if (!root) {
      setChip(null);
      return;
    }
    const range = selectionInside(root);
    setChip(range ? chipFromRange(range) : null);
  }, []);

  useEffect(() => {
    setShowSource(false);
  }, [content]);

  useEffect(() => {
    const onPointerUp = () => {
      requestAnimationFrame(syncChip);
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setChip(null);
        return;
      }
      if (e.shiftKey || e.key.startsWith('Arrow')) requestAnimationFrame(syncChip);
    };
    const onScroll = () => setChip(null);
    document.addEventListener('mouseup', onPointerUp);
    document.addEventListener('touchend', onPointerUp, { passive: true });
    document.addEventListener('keyup', onKeyUp);
    window.addEventListener('scroll', onScroll, true);
    return () => {
      document.removeEventListener('mouseup', onPointerUp);
      document.removeEventListener('touchend', onPointerUp);
      document.removeEventListener('keyup', onKeyUp);
      window.removeEventListener('scroll', onScroll, true);
    };
  }, [syncChip]);

  const runExplain = (quote: string) => {
    setChip(null);
    window.getSelection()?.removeAllRanges();
    explainNotesQuote(quote);
  };

  const hasBody = content.trim().length > 0;

  return (
    <div
      className={`preview-content markdown${inspectable ? ' is-inspectable' : ''}`}
      ref={setRoot}
      data-testid="note-preview"
      onContextMenu={(e) => {
        const root = rootRef.current;
        if (!root) return;
        const range = selectionInside(root);
        const next = range ? chipFromRange(range) : null;
        if (!next) return;
        e.preventDefault();
        setChip({ ...next, x: e.clientX, y: e.clientY, below: true });
      }}
    >
      {title ? <h1 className="preview-h1">{title}</h1> : null}
      {hasBody ? (
        <p className="notes-explain-hint">
          拖选词语或句子，点「{EXPLAINER_NAME} 讲解」；已选中时可右键。
          {inspectable ? (
            <>
              {' '}
              <button
                type="button"
                className="notes-preview-source-btn"
                onClick={() => setShowSource((s) => !s)}
              >
                {showSource ? '看渲染' : '看源码'}
              </button>
            </>
          ) : null}
        </p>
      ) : null}
      {!hasBody ? (
        <p className="muted">暂无正文</p>
      ) : showSource ? (
        <pre className="preview-block-source" aria-label="Markdown 源码">{content}</pre>
      ) : (
        <MarkdownRenderer content={content} remarkPlugins={NOTE_PREVIEW_REMARK} />
      )}
      {noteId ? (
        <>
          <TocPanel noteId={noteId} />
          <BacklinkPanel noteId={noteId} />
        </>
      ) : null}
      {chip
        ? createPortal(
            <div
              className={`notes-explain-chip${chip.below ? ' is-below' : ''}`}
              style={{ left: chip.x, top: chip.y }}
              data-testid="notes-explain-chip"
            >
              <button
                type="button"
                className="notes-explain-chip__btn"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => runExplain(chip.quote)}
              >
                {EXPLAINER_NAME} 讲解
              </button>
            </div>,
            document.body,
          )
        : null}
    </div>
  );
});
