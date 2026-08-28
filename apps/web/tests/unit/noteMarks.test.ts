import { describe, expect, it } from 'vitest';
import {
  applyNoteHighlight,
  applyNoteHighlightInDoc,
  expandHighlightRange,
  flattenMultilineMarks,
  parseNoteHighlight,
  remarkNoteMarks,
  scanMarks,
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

  it('选区恰好是 inner 时扩到整段标记', () => {
    const doc = '前==cool:中间件==后';
    const innerFrom = doc.indexOf('中间件');
    expect(expandHighlightRange(doc, innerFrom, innerFrom + 3)).toEqual({
      from: doc.indexOf('==cool:'),
      to: doc.indexOf('后'),
    });
  });

  it('多行按行着色,列表与标题前缀留在标记外', () => {
    expect(applyNoteHighlight('第一段\n\n第二段', 'cool')).toBe(
      '==cool:第一段==\n\n==cool:第二段==',
    );
    expect(applyNoteHighlight('- aa\n- bb', 'rose')).toBe('- ==rose:aa==\n- ==rose:bb==');
    expect(applyNoteHighlight('## 标题\n正文', 'warm')).toBe('## ==warm:标题==\n==warm:正文==');
    expect(applyNoteHighlight('==cool:a==\n==cool:b==', 'cool')).toBe('a\nb');
  });

  it('更大选区套住已有底纹时拆平再包,不嵌套', () => {
    const doc = 'aaa==warm:bbb==ccc';
    const next = applyNoteHighlightInDoc(doc, 0, doc.length, 'cool');
    expect(next).toBe('==cool:aaabbbccc==');
    expect(next.includes('==warm:')).toBe(false);
    expect(scanMarks(next)).toHaveLength(1);
  });

  it('在已有底纹内部换色则拆成三段,不套娃', () => {
    const doc = '==warm:AAABBBCCC==';
    const from = doc.indexOf('BBB');
    const next = applyNoteHighlightInDoc(doc, from, from + 3, 'cool');
    expect(next).toBe('==warm:AAA====cool:BBB====warm:CCC==');
    expect(scanMarks(next).map((m) => next.slice(m.innerStart, m.innerEnd))).toEqual([
      'AAA',
      'BBB',
      'CCC',
    ]);
  });

  it('去掉底纹能清掉正文里未闭合的 ==rose: 前缀', () => {
    const doc = '==rose:hello\nworld';
    expect(applyNoteHighlightInDoc(doc, 0, doc.length, 'clear')).toBe('hello\nworld');
  });

  it('去掉底纹能清掉围栏里未闭合的 ==rose: 前缀', () => {
    const doc = '```\n==rose:+-----+\n==rose:| box |\n==rose:+-----+\n```\n';
    const next = applyNoteHighlightInDoc(doc, 0, doc.length, 'clear');
    expect(next.includes('==rose:')).toBe(false);
    expect(next).toContain('+-----+');
    expect(next).toContain('| box |');
    expect(next).toContain('```');
  });

  it('去掉底纹能清掉围栏里误写入的标记', () => {
    const doc = '```\n==rose:| gateway |\n==\n```\n正文';
    const next = applyNoteHighlightInDoc(doc, 0, doc.length, 'clear');
    expect(next).toContain('| gateway |');
    expect(next.includes('==rose:')).toBe(false);
    expect(next.startsWith('```')).toBe(true);
  });

  it('代码围栏内不写入底纹', () => {
    const doc = '```\nhello\n```\n\nhello 正文';
    const from = doc.indexOf('hello');
    const next = applyNoteHighlightInDoc(doc, from, from + 5, 'warm');
    expect(next.startsWith('```\nhello\n```')).toBe(true);
    const body = doc.lastIndexOf('hello');
    const painted = applyNoteHighlightInDoc(doc, body, body + 5, 'warm');
    expect(painted).toContain('==warm:hello== 正文');
    expect(painted.startsWith('```\nhello\n```')).toBe(true);
  });

  it('大段含加粗的选区按行包一层,源码不嵌套', () => {
    const doc = '1. **学习与了解** 说明\n2. 第二点';
    const next = applyNoteHighlight(doc, 'cool');
    expect(next).toBe('1. ==cool:**学习与了解** 说明==\n2. ==cool:第二点==');
    expect(scanMarks(next)).toHaveLength(2);
  });

  it('渲染前把旧的跨段标记拆成每行一条', () => {
    expect(flattenMultilineMarks('前==cool:上\n\n下==后')).toBe(
      '前==cool:上==\n\n==cool:下==后',
    );
  });

  it('四反引号围栏不被三反引号提前关掉', () => {
    const doc = '````\nconst x = 1\n```\nstill code\n````\n正文';
    const from = doc.indexOf('still');
    const skipped = applyNoteHighlightInDoc(doc, from, from + 10, 'rose');
    expect(skipped).toContain('still code');
    expect(skipped.includes('==rose:still')).toBe(false);
    const body = doc.indexOf('正文');
    const painted = applyNoteHighlightInDoc(doc, body, body + 2, 'rose');
    expect(painted).toContain('==rose:正文==');
  });

  it('去掉底纹不删代码块里的字面 ==a==', () => {
    const doc = '```\nconst pattern = "==a=="\n```\n';
    const next = applyNoteHighlightInDoc(doc, 0, doc.length, 'clear');
    expect(next).toContain('const pattern = "==a=="');
  });

  it('套住已损坏的嵌套标记能拆平再包', () => {
    const doc = '==cool:outer ==warm:inner== tail==';
    const next = applyNoteHighlightInDoc(doc, 0, doc.length, 'lime');
    expect(next.includes('==cool:')).toBe(false);
    expect(next.includes('==warm:')).toBe(false);
    expect(next.startsWith('==lime:')).toBe(true);
    expect(next.includes('inner')).toBe(true);
  });

  it('行内代码内不写入底纹', () => {
    const doc = 'see `hello` please hello';
    const from = doc.indexOf('hello');
    const skipped = applyNoteHighlightInDoc(doc, from, from + 5, 'warm');
    expect(skipped).toContain('`hello`');
    expect(skipped.includes('==warm:hello==')).toBe(false);
    const body = doc.lastIndexOf('hello');
    const painted = applyNoteHighlightInDoc(doc, body, body + 5, 'warm');
    expect(painted).toContain('`hello` please ==warm:hello==');
  });

  it('整行含行内代码时整包,不在反引号两侧拆', () => {
    const doc = '行内 `hello` 外面';
    expect(applyNoteHighlight(doc, 'cool')).toBe('==cool:行内 `hello` 外面==');
  });

  it('ASCII 框线与表格行整行不上底纹,单元格内文字可以', () => {
    const box = '+-----+\n| box |\n+-----+';
    expect(applyNoteHighlight(box, 'rose')).toBe(box);
    const table = '| a | b |\n| - | - |\n| c | d |';
    expect(applyNoteHighlight(table, 'cool')).toBe(table);
    const cell = '| hello |';
    const from = cell.indexOf('hello');
    expect(applyNoteHighlightInDoc(cell, from, from + 5, 'lime')).toBe('| ==lime:hello== |');
  });

  it('切出 mark 节点且不误伤代码围栏外的普通字', () => {
    const nodes = splitMarkedText('见 ==cool:中间件== 与 ==暖==');
    expect(nodes.map((n) => n.type)).toEqual(['text', 'mark', 'text', 'mark']);
    expect(nodes[1].data?.hProperties).toEqual({ className: ['notes-hl-cool'] });
    expect((nodes[1].children as { value: string }[])[0].value).toBe('中间件');
    expect(nodes[3].data?.hProperties).toEqual({ className: ['notes-hl-warm'] });
  });

  it('预览把加粗包进 mark,不把 == 漏出去', () => {
    const tree = {
      type: 'root',
      children: [
        {
          type: 'paragraph',
          children: [
            { type: 'text', value: '==cool:' },
            { type: 'strong', children: [{ type: 'text', value: '学习与了解' }] },
            { type: 'text', value: ' 说明==' },
          ],
        },
      ],
    };
    remarkNoteMarks()(tree);
    const p = tree.children[0];
    expect(p.children.map((n) => n.type)).toEqual(['mark']);
    const mark = p.children[0];
    expect(mark.data?.hProperties).toEqual({ className: ['notes-hl-cool'] });
    expect(mark.children?.map((n) => n.type)).toEqual(['strong', 'text']);
    const texts = JSON.stringify(tree);
    expect(texts.includes('==')).toBe(false);
  });
});
