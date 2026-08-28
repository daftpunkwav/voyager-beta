/** 笔记预览 Markdown:底纹/围栏恢复走页面模块,不污染公共渲染器。 */

import type { CSSProperties } from 'react';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
import { notesHlMarkProps, recoverTonedMarkup } from './noteHl';
import { flattenMultilineMarks } from './noteMarkApply';
import { NOTE_PREVIEW_REMARK } from './noteMarkRemark';

function noteMarkProps(className?: string): { className: string; style?: CSSProperties } {
  const hl = notesHlMarkProps(className);
  return {
    className: hl.className,
    style: hl.color ? { ['--notes-hl' as string]: hl.color } : undefined,
  };
}

export function NoteMarkdown({ content, className }: { content: string; className?: string }) {
  return (
    <MarkdownRenderer
      content={flattenMultilineMarks(content)}
      className={className}
      remarkPlugins={NOTE_PREVIEW_REMARK}
      recoverCodeMarkup={recoverTonedMarkup}
      markProps={noteMarkProps}
    />
  );
}
