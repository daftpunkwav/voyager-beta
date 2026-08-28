import { describe, expect, it } from 'vitest';
import { splitMarkdownBlocks } from '@/pages/notes/noteBlocks';

describe('splitMarkdownBlocks', () => {
  it('空文档没有块', () => {
    expect(splitMarkdownBlocks('')).toEqual([]);
    expect(splitMarkdownBlocks('   \n\n')).toEqual([]);
  });

  it('标题单独成块,源码保留 ##', () => {
    const blocks = splitMarkdownBlocks('## 你好\n\n一段正文');
    expect(blocks).toHaveLength(2);
    expect(blocks[0].source).toBe('## 你好');
    expect(blocks[0].startLine).toBe(1);
    expect(blocks[1].source).toBe('一段正文');
    expect(blocks[1].startLine).toBe(3);
  });

  it('围栏代码记下起始行', () => {
    const md = ['前言', '', '```js', 'const n = 1;', '```'].join('\n');
    const blocks = splitMarkdownBlocks(md);
    expect(blocks[1].startLine).toBe(3);
    expect(blocks[1].source).toContain('```js');
  });

  it('围栏代码与列表保持整块', () => {
    const md = ['```js', 'const n = 1;', '```', '', '- a', '- b'].join('\n');
    const blocks = splitMarkdownBlocks(md);
    expect(blocks).toHaveLength(2);
    expect(blocks[0].source).toContain('```js');
    expect(blocks[1].source).toBe('- a\n- b');
  });
});
