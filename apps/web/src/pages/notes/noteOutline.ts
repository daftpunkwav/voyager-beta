/** 笔记目录大纲:与后端 extract_toc 同语义(跳过围栏,行号 1 基)。 */

import { NOTE_HL_KIND } from './noteHl';

export interface NoteTocItem {
  level: number;
  text: string;
  line: number;
}

export function extractNoteToc(content: string): NoteTocItem[] {
  const toc: NoteTocItem[] = [];
  let inFence = false;
  let fenceMarker = '';
  const lines = content.replace(/\r\n/g, '\n').split('\n');
  for (let i = 0; i < lines.length; i += 1) {
    const stripped = lines[i].replace(/^\s+/, '');
    const marker = stripped.slice(0, 3);
    if (marker === '```' || marker === '~~~') {
      if (!inFence) {
        inFence = true;
        fenceMarker = marker;
      } else if (marker === fenceMarker) {
        inFence = false;
      }
      continue;
    }
    if (inFence || !stripped.startsWith('#')) continue;
    const m = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(stripped);
    if (m) toc.push({ level: m[1].length, text: m[2].trim(), line: i + 1 });
  }
  return toc;
}

/** 目录展示与 slug 用可见标题,去掉底纹标记,对齐预览 nodeText。 */
export function tocHeadingLabel(text: string): string {
  const stripped = text.replace(new RegExp(`==(${NOTE_HL_KIND}):`, 'gi'), '').replace(/==/g, '').trim();
  return stripped || text;
}
