import { describe, expect, it } from 'vitest';
import {
  toggleFence,
  toggleInlineFormat,
  toggleInlineFormatInDoc,
  toggleLinePrefixBlock,
} from '@/pages/notes/noteFormat';

describe('toggleInlineFormat 斜体', () => {
  it('选中明文则套上,再点同一段去掉', () => {
    expect(toggleInlineFormat('中间件', 'em')).toBe('*中间件*');
    expect(toggleInlineFormat('*中间件*', 'em')).toBe('中间件');
  });

  it('超集含斜体与正常体时全部变为斜体,再点还原', () => {
    expect(toggleInlineFormat('看 *中间件* 再看', 'em')).toBe('*看 中间件 再看*');
    expect(toggleInlineFormat('*看 中间件 再看*', 'em')).toBe('看 中间件 再看');
  });

  it('选中不含星号的内层也能去掉斜体', () => {
    const doc = '前*中间件*后';
    const inner = doc.indexOf('中间件');
    const { next } = toggleInlineFormatInDoc(doc, inner, inner + 3, 'em');
    expect(next).toBe('前中间件后');
  });

  it('加粗文字上斜体变成粗斜体,再点斜体只去掉斜体', () => {
    expect(toggleInlineFormat('**粗**', 'em')).toBe('***粗***');
    expect(toggleInlineFormat('***粗***', 'em')).toBe('**粗**');
  });
});

describe('toggleInlineFormat 加粗', () => {
  it('选中明文则套上,再点去掉', () => {
    expect(toggleInlineFormat('标题', 'strong')).toBe('**标题**');
    expect(toggleInlineFormat('**标题**', 'strong')).toBe('标题');
  });

  it('超集含加粗与正常体时全部加粗,再点还原', () => {
    expect(toggleInlineFormat('看 **标题** 完', 'strong')).toBe('**看 标题 完**');
    expect(toggleInlineFormat('**看 标题 完**', 'strong')).toBe('看 标题 完');
  });

  it('选中内层也能去掉加粗', () => {
    const doc = '前**标题**后';
    const inner = doc.indexOf('标题');
    const { next } = toggleInlineFormatInDoc(doc, inner, inner + 2, 'strong');
    expect(next).toBe('前标题后');
  });

  it('粗斜体再点加粗只留斜体', () => {
    expect(toggleInlineFormat('***粗***', 'strong')).toBe('*粗*');
  });
});

describe('toggleInlineFormat 删除线/代码/链接', () => {
  it('删除线开关与超集', () => {
    expect(toggleInlineFormat('废', 'strike')).toBe('~~废~~');
    expect(toggleInlineFormat('~~废~~', 'strike')).toBe('废');
    expect(toggleInlineFormat('a ~~b~~ c', 'strike')).toBe('~~a b c~~');
  });

  it('行内代码开关与超集', () => {
    expect(toggleInlineFormat('x', 'code')).toBe('`x`');
    expect(toggleInlineFormat('`x`', 'code')).toBe('x');
    expect(toggleInlineFormat('a `b` c', 'code')).toBe('`a b c`');
  });

  it('链接套上与去掉,超集抽掉已有链接再包一层', () => {
    expect(toggleInlineFormat('文档', 'link')).toBe('[文档](https://)');
    expect(toggleInlineFormat('[文档](https://)', 'link')).toBe('文档');
    expect(toggleInlineFormat('见 [文档](https://x) 页', 'link')).toBe('[见 文档 页](https://)');
  });
});

describe('toggleFence / 行前缀块', () => {
  it('代码围栏再点去掉', () => {
    expect(toggleFence('hello')).toBe('```\nhello\n```');
    expect(toggleFence('```\nhello\n```')).toBe('hello');
  });

  it('多行有的已是列表有的不是,一次全部套上,再点全部去掉', () => {
    expect(toggleLinePrefixBlock('- a\nb', '- ')).toBe('- a\n- b');
    expect(toggleLinePrefixBlock('- a\n- b', '- ')).toBe('a\nb');
  });

  it('标题/引用同样按整段统一', () => {
    expect(toggleLinePrefixBlock('## a\nb', '## ')).toBe('## a\n## b');
    expect(toggleLinePrefixBlock('## a\n## b', '## ')).toBe('a\nb');
    expect(toggleLinePrefixBlock('> a\nb', '> ')).toBe('> a\n> b');
  });
});
