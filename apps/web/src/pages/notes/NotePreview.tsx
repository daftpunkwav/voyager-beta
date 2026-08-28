/** 笔记预览:分栏只渲染;纯预览可点选块查看 Markdown 源码。 */

import { useMemo, useState } from 'react';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
import { BacklinkPanel, TocPanel } from './NoteFeatures';
import { splitMarkdownBlocks } from './noteBlocks';

interface NotePreviewProps {
  title: string;
  content: string;
  noteId: string | null;
  /** 纯预览:点击块显示源码(如 `## 你好`);分栏关闭此行为 */
  inspectable?: boolean;
  onScrollEl?: (el: HTMLDivElement | null) => void;
  /** 分栏时点击块跳到编辑器对应行 */
  onJumpToLine?: (line: number) => void;
}

export function NotePreview({
  title,
  content,
  noteId,
  inspectable = false,
  onScrollEl,
  onJumpToLine,
}: NotePreviewProps) {
  const blocks = useMemo(() => splitMarkdownBlocks(content), [content]);
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <div
      className={`preview-content markdown${inspectable ? ' is-inspectable' : ''}`}
      ref={onScrollEl}
      data-testid="note-preview"
    >
      {title ? <h1 className="preview-h1">{title}</h1> : null}
      {blocks.length === 0 ? (
        <p className="muted">暂无正文</p>
      ) : (
        blocks.map((block) => {
          const open = inspectable && openId === block.id;
          return (
            <div
              key={block.id}
              className={`preview-block${open ? ' is-open' : ''}${inspectable || onJumpToLine ? ' is-hot' : ''}`}
              data-start-line={block.startLine}
              role={inspectable || onJumpToLine ? 'button' : undefined}
              tabIndex={inspectable || onJumpToLine ? 0 : undefined}
              onClick={(e) => {
                if ((e.target as HTMLElement).closest('a, button')) return;
                const sel = window.getSelection();
                if (sel && sel.toString().length > 0) return;
                if (inspectable) {
                  setOpenId(open ? null : block.id);
                  return;
                }
                onJumpToLine?.(block.startLine);
              }}
              onKeyDown={(e) => {
                if (e.key !== 'Enter' && e.key !== ' ') return;
                e.preventDefault();
                if (inspectable) setOpenId(open ? null : block.id);
                else onJumpToLine?.(block.startLine);
              }}
            >
              {open ? (
                <pre className="preview-block-source" aria-label="Markdown 源码">
                  {block.source}
                </pre>
              ) : null}
              <div className="preview-block-render">
                <MarkdownRenderer content={block.source} />
              </div>
            </div>
          );
        })
      )}
      {noteId ? (
        <>
          <TocPanel noteId={noteId} />
          <BacklinkPanel noteId={noteId} />
        </>
      ) : null}
    </div>
  );
}
