import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { render, screen } from '@testing-library/react';
import { looksLikeMermaid } from '@/components/common/MermaidBlock';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';

describe('looksLikeMermaid', () => {
  it('仅识别 language-mermaid', () => {
    expect(looksLikeMermaid('mermaid', 'graph TD\nA-->B')).toBe(true);
    expect(looksLikeMermaid('MERMAID', '')).toBe(true);
  });

  it('无语言标记的 graph 不走 Mermaid（缩小 XSS 面）', () => {
    expect(looksLikeMermaid(null, 'graph TD\nA-->B')).toBe(false);
    expect(looksLikeMermaid('text', 'flowchart LR\nA-->B')).toBe(false);
    expect(looksLikeMermaid(null, 'sequenceDiagram\nA->>B: hi')).toBe(false);
  });

  it('普通代码不误判', () => {
    expect(looksLikeMermaid('python', 'print("hi")')).toBe(false);
    expect(looksLikeMermaid(null, 'const x = 1')).toBe(false);
  });
});

describe('MarkdownRenderer mermaid', () => {
  it('普通段落可渲染（冒烟）', () => {
    render(createElement(MarkdownRenderer, { content: 'hello **world**' }));
    expect(screen.getByText('world')).toBeTruthy();
  });

  it('mermaid fence 走 MermaidBlock（初始 fallback）', () => {
    const md = '```mermaid\ngraph TD\n  A-->B\n```';
    render(createElement(MarkdownRenderer, { content: md }));
    expect(screen.getByTestId('mermaid-fallback')).toBeTruthy();
  });

  it('无语言 graph TD 不走 MermaidBlock', () => {
    const md = '```\ngraph TD\n  A-->B\n```';
    render(createElement(MarkdownRenderer, { content: md }));
    expect(screen.queryByTestId('mermaid-fallback')).toBeNull();
    expect(screen.queryByTestId('mermaid-svg')).toBeNull();
  });
});
