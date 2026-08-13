import { useEffect, useId, useState } from 'react';
import DOMPurify from 'dompurify';
import type { Config as DompurifyConfig } from 'dompurify';

/** 仅显式 ```mermaid fence，避免把普通代码误送入 SVG 注入路径 */
export function looksLikeMermaid(lang: string | null | undefined, _code?: string): boolean {
  return (lang || '').toLowerCase() === 'mermaid';
}

interface MermaidBlockProps {
  code: string;
}

const SVG_PURIFY: DompurifyConfig = {
  USE_PROFILES: { svg: true, svgFilters: true },
  ADD_TAGS: ['use'],
  FORBID_TAGS: ['script', 'foreignObject', 'iframe', 'object', 'embed', 'a'],
  FORBID_ATTR: ['onclick', 'onload', 'onerror', 'onmouseover', 'href', 'xlink:href'],
};

/**
 * 客户端 Mermaid → 消毒后的 SVG；失败或未通过消毒时降级为代码块。
 */
export function MermaidBlock({ code }: MermaidBlockProps) {
  const reactId = useId().replace(/:/g, '');
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setSvg(null);
    setFailed(false);

    (async () => {
      try {
        const mermaid = (await import('mermaid')).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: 'dark',
          securityLevel: 'strict',
          fontFamily: 'inherit',
        });
        const { svg: rendered } = await mermaid.render(`mmd-${reactId}`, code);
        const clean = DOMPurify.sanitize(rendered, SVG_PURIFY);
        if (!clean || !clean.includes('<svg')) {
          throw new Error('svg sanitized empty');
        }
        if (!cancelled) setSvg(clean);
      } catch {
        if (!cancelled) {
          setFailed(true);
          setSvg(null);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [code, reactId]);

  if (failed || !svg) {
    return (
      <div className="md-codeblock md-mermaid--fallback" data-testid="mermaid-fallback">
        <div className="md-codeblock__lang">mermaid</div>
        <pre className="hljs">
          <code>{code}</code>
        </pre>
      </div>
    );
  }

  return (
    <div
      className="md-mermaid"
      data-testid="mermaid-svg"
      // §4.2.15: svg 已在上方经 DOMPurify.sanitize(..., SVG_PURIFY) 清洗
      // eslint-disable-next-line no-restricted-syntax
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
