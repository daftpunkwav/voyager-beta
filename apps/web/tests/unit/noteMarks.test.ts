import { describe, expect, it } from 'vitest';
import {
  applyNoteHighlight,
  expandHighlightRange,
  parseNoteHighlight,
  splitMarkedText,
  toggleNoteHighlight,
  wrapNoteHighlight,
} from '@/pages/notes/noteMarks';

describe('noteMarks', () => {
  it('解析带色标与裸 ==text==', () => {
    expect(parseNoteHighlight('==cool:中间件==')).toEqual({ tone: 'cool', inner: '中间件' });
    expect(parseNoteHighlight('==中间件==')).toEqual({ tone: 'warm', inner: '中间件' });
    expect(parseNoteHighlight('普通')).toBeNull();
  });

  it('工具栏同色再点则去掉,换色则改写', () => {
    expect(toggleNoteHighlight('中间件', 'cool')).toBe('==cool:中间件==');
    expect(toggleNoteHighlight('==cool:中间件==', 'cool')).toBe('中间件');
    expect(toggleNoteHighlight('==cool:中间件==', 'rose')).toBe('==rose:中间件==');
    expect(applyNoteHighlight('==warm:中间件==', 'clear')).toBe('中间件');
    expect(wrapNoteHighlight('x', 'lime')).toBe('==lime:x==');
  });

  it('选区内侧时扩到整段标记', () => {
    const doc = '前==cool:中间件==后';
    const innerFrom = doc.indexOf('中间件');
    expect(expandHighlightRange(doc, innerFrom, innerFrom + 3)).toEqual({
      from: doc.indexOf('==cool:'),
      to: doc.indexOf('后'),
    });
  });

  it('切出 mark 节点且不误伤代码围栏外的普通字', () => {
    const nodes = splitMarkedText('见 ==cool:中间件== 与 ==暖==');
    expect(nodes.map((n) => n.type)).toEqual(['text', 'mark', 'text', 'mark']);
    expect(nodes[1].data?.hProperties).toEqual({ className: ['notes-hl-cool'] });
    expect((nodes[1].children as { value: string }[])[0].value).toBe('中间件');
    expect(nodes[3].data?.hProperties).toEqual({ className: ['notes-hl-warm'] });
  });
});
