/** Markdown 渲染器:GFM/highlight/sanitize/Mermaid/ASCII 架构图/表格横滚 +
 *  标题锚点(TOC)/代码块复制/图片灯箱/[[内链]]/外链新标签。
 *
 * 安全:rehype-sanitize 纵深防御保留;schema 只按最小面放宽
 * (highlight className、attachment: 与 /api/ 相对图源、a 的 target/rel)。
 */

import { Children, isValidElement, useState, type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import type { Options as SanitizeOptions } from 'rehype-sanitize';
import GithubSlugger from 'github-slugger';
import { cn } from '@/utils/cn';
import { tryParseAsciiArchLayers, looksLikeMarkdownTable } from '@/utils/asciiArch';
import { looksLikeMermaid, MermaidBlock } from '@/components/common/MermaidBlock';
import { Lightbox } from '@/components/common/Lightbox';

interface MarkdownRendererProps {
  content: string;
  className?: string;
  /** 内部二次渲染时关闭「代码块内表格救援」，避免递归 */
  disableTableRescue?: boolean;
  /** 内链 [[目标]] 点击回调;缺省按标题导航 /notes?note=<id> 语义交由上层(灰显) */
  onWikiLink?: (target: string) => void;
}

/** 允许 highlight.js 注入的 class,避免 sanitize 洗掉着色;
 *  图源放行 attachment:(自定义 scheme)与站点内 /api/ 相对路径;
 *  a 放行 target/rel(外链新标签)。 */
const sanitizeSchema: SanitizeOptions = {
  ...defaultSchema,
  protocols: {
    ...defaultSchema.protocols,
    src: [...(defaultSchema.protocols?.src ?? []), 'attachment'],
  },
  attributes: {
    ...defaultSchema.attributes,
    code: [...(defaultSchema.attributes?.code ?? []), ['className']],
    span: [...(defaultSchema.attributes?.span ?? []), ['className']],
    pre: [...(defaultSchema.attributes?.pre ?? []), ['className']],
    a: [...(defaultSchema.attributes?.a ?? []), 'target', 'rel'],
    h1: [...(defaultSchema.attributes?.h1 ?? []), 'id'],
    h2: [...(defaultSchema.attributes?.h2 ?? []), 'id'],
    h3: [...(defaultSchema.attributes?.h3 ?? []), 'id'],
    h4: [...(defaultSchema.attributes?.h4 ?? []), 'id'],
    h5: [...(defaultSchema.attributes?.h5 ?? []), 'id'],
    h6: [...(defaultSchema.attributes?.h6 ?? []), 'id'],
    img: [...(defaultSchema.attributes?.img ?? []), ['className', 'loading']],
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

/** [[目标|别名]] → Markdown 链接(#wiki: scheme);跳过代码围栏(与后端 resolve_links 同语义)。 */
export function preprocessWikiLinks(content: string): string {
  const segments = content.split(/(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)/);
  const WIKI = /\[\[([^\]|\n]+)(?:\|([^\]\n]*))?\]\]/g;
  return segments
    .map((seg, i) => {
      if (i % 2 === 1) return seg; // 代码围栏/行内代码段原样保留
      return seg.replace(WIKI, (_m, target: string, alias?: string) => {
        const label = (alias ?? target).trim();
        return `[${label}](#wiki:${target.trim()})`;
      });
    })
    .join('');
}

function CodeCopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="md-codeblock__copy"
      aria-label="复制代码"
      onClick={async (e) => {
        e.preventDefault();
        e.stopPropagation();
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          /* 剪贴板不可用(非安全上下文):按钮态不变,不假装成功 */
        }
      }}
    >
      {copied ? '已复制' : '复制'}
    </button>
  );
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
  onWikiLink,
}: MarkdownRendererProps) {
  const [lightbox, setLightbox] = useState<{ src: string; alt: string } | null>(null);
  // slugger 有内部去重计数器:每次渲染新实例,避免跨渲染串号
  const slugs = new GithubSlugger();
  const prepared = preprocessWikiLinks(content);

  return (
    <div className={cn('markdown markdown-body', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[
          [rehypeHighlight, { detect: true, ignoreMissing: true }],
          [rehypeSanitize, sanitizeSchema],
        ]}
        components={{
          h1: ({ children, ...props }) => {
            const id = slugs.slug(nodeText(children));
            return <h1 {...props} id={id}>{children}</h1>;
          },
          h2: ({ children, ...props }) => {
            const id = slugs.slug(nodeText(children));
            return <h2 {...props} id={id}>{children}</h2>;
          },
          h3: ({ children, ...props }) => {
            const id = slugs.slug(nodeText(children));
            return <h3 {...props} id={id}>{children}</h3>;
          },
          h4: ({ children, ...props }) => {
            const id = slugs.slug(nodeText(children));
            return <h4 {...props} id={id}>{children}</h4>;
          },
          h5: ({ children, ...props }) => {
            const id = slugs.slug(nodeText(children));
            return <h5 {...props} id={id}>{children}</h5>;
          },
          h6: ({ children, ...props }) => {
            const id = slugs.slug(nodeText(children));
            return <h6 {...props} id={id}>{children}</h6>;
          },
          a: ({ children, href, ...props }) => {
            if (typeof href === 'string' && href.startsWith('#wiki:')) {
              const target = decodeURIComponent(href.slice('#wiki:'.length));
              return (
                <a
                  {...props}
                  href={`/notes?note=${encodeURIComponent(target)}`}
                  className="md-wiki-link"
                  title={`内链:${target}`}
                  onClick={(e) => {
                    e.preventDefault();
                    if (onWikiLink) onWikiLink(target);
                    else window.location.href = `/notes?note=${encodeURIComponent(target)}`;
                  }}
                >
                  {children}
                </a>
              );
            }
            return (
              <a {...props} href={href} target="_blank" rel="noreferrer noopener">
                {children}
              </a>
            );
          },
          img: ({ src, alt, ...props }) => {
            const resolved =
              typeof src === 'string' && src.startsWith('attachment://')
                ? `/api/notes/assets/${src.slice('attachment://'.length)}`
                : typeof src === 'string' ? src : undefined;
            if (!resolved) return null;
            return (
              <img
                {...props}
                src={resolved}
                alt={alt ?? ''}
                loading="lazy"
                className="md-img"
                onClick={() => setLightbox({ src: resolved, alt: alt ?? '' })}
              />
            );
          },
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
                <div className="md-codeblock__bar">
                  {lang && <div className="md-codeblock__lang">{lang}</div>}
                  <CodeCopyButton text={text} />
                </div>
                <pre className="hljs">{children}</pre>
              </div>
            );
          },
        }}
      >
        {prepared}
      </ReactMarkdown>
      <Lightbox src={lightbox?.src ?? null} alt={lightbox?.alt} onClose={() => setLightbox(null)} />
    </div>
  );
}
