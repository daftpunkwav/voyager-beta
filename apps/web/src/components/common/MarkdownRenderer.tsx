import { Children, isValidElement, type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import type { Options as SanitizeOptions } from 'rehype-sanitize';
import { cn } from '@/utils/cn';
import { tryParseAsciiArchLayers, looksLikeMarkdownTable } from '@/utils/asciiArch';
import { looksLikeMermaid, MermaidBlock } from '@/components/common/MermaidBlock';

interface MarkdownRendererProps {
  content: string;
  className?: string;
  /** 内部二次渲染时关闭「代码块内表格救援」，避免递归 */
  disableTableRescue?: boolean;
}

/** 允许 highlight.js 注入的 class，避免 sanitize 洗掉着色 */
const sanitizeSchema: SanitizeOptions = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    code: [...(defaultSchema.attributes?.code ?? []), ['className']],
    span: [...(defaultSchema.attributes?.span ?? []), ['className']],
    pre: [...(defaultSchema.attributes?.pre ?? []), ['className']],
  },
};

function nodeText(node: ReactNode): string {
  if (node == null || typeof node === 'boolean') return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(nodeText).join('');
  if (isValidElement<{ children?: ReactNode }>(node)) {
    return nodeText(node.props.children);
  }
  return '';
}

function extractCodeLang(children: ReactNode): string | null {
  for (const child of Children.toArray(children)) {
    if (!isValidElement<{ className?: string }>(child)) continue;
    const cls = child.props.className ?? '';
    const m =
      /\blanguage-([a-z0-9_+-]+)\b/i.exec(cls) ||
      /\bhljs\s+([a-z0-9_+-]+)\b/i.exec(cls);
    if (m?.[1] && m[1].toLowerCase() !== 'hljs') return m[1].toLowerCase();
  }
  return null;
}

function ArchStack({
  layers,
}: {
  layers: NonNullable<ReturnType<typeof tryParseAsciiArchLayers>>;
}) {
  return (
    <div className="md-arch-stack" role="img" aria-label="架构层级图">
      {layers.map((layer, i) => (
        <div key={`${layer.title}-${i}`} className="md-arch-stack__layer">
          <div className="md-arch-stack__index">{i + 1}</div>
          <div className="md-arch-stack__body">
            <div className="md-arch-stack__title">{layer.title}</div>
            {layer.lines.length > 0 && (
              <ul className="md-arch-stack__lines">
                {layer.lines.map((line, j) => (
                  <li key={`${j}-${line.slice(0, 24)}`}>{line}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export function MarkdownRenderer({
  content,
  className,
  disableTableRescue = false,
}: MarkdownRendererProps) {
  return (
    <div className={cn('markdown markdown-body', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[
          [rehypeHighlight, { detect: true, ignoreMissing: true }],
          [rehypeSanitize, sanitizeSchema],
        ]}
        components={{
          table: ({ children, ...props }) => (
            <div className="markdown-table-wrap">
              <table {...props}>{children}</table>
            </div>
          ),
          pre: ({ children }) => {
            const text = Children.toArray(children).map(nodeText).join('');
            // 代码块里误塞的 Markdown 表格：按 Markdown 再渲染，避免当成架构卡或纯文本
            if (!disableTableRescue && looksLikeMarkdownTable(text)) {
              return (
                <div className="md-table-rescue">
                  <MarkdownRenderer content={text} disableTableRescue />
                </div>
              );
            }
            const layers = tryParseAsciiArchLayers(text);
            if (layers) return <ArchStack layers={layers} />;
            const lang = extractCodeLang(children);
            if (looksLikeMermaid(lang, text)) {
              return <MermaidBlock code={text} />;
            }
            return (
              <div className="md-codeblock">
                {lang && <div className="md-codeblock__lang">{lang}</div>}
                <pre className="hljs">{children}</pre>
              </div>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
