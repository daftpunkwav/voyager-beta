import { useEffect, useState } from 'react';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
import {
  coalesceEmptyBodyWithThinking,
  isDispatchNoticeOnly,
  isStatusLine,
  isStatusOnlyThinking,
  partitionThinking,
  persistableThinking,
} from '@/utils/agentThinking';

export {
  coalesceEmptyBodyWithThinking,
  isDispatchNoticeOnly,
  isStatusLine,
  isStatusOnlyThinking,
  partitionThinking,
  persistableThinking,
};

interface StreamRendererProps {
  content: string;
  thinking?: string;
  streaming: boolean;
  /** 是否默认展开思考区；默认收起 */
  thinkingOpen?: boolean;
  /** 仅折叠正文，不影响思考区（长文折叠用） */
  collapseBody?: boolean;
}

/** 流式 Markdown；真实思考默认收起，脚手架不进思考面板 */
export function StreamRenderer({
  content,
  thinking,
  streaming,
  thinkingOpen = false,
  collapseBody = false,
}: StreamRendererProps) {
  const coalesced = coalesceEmptyBodyWithThinking(content, thinking);
  const displayContent = coalesced.content;
  const displayThinking = coalesced.thinking;

  const [rendered, setRendered] = useState(displayContent);
  const [thinkingExpanded, setThinkingExpanded] = useState(thinkingOpen);

  useEffect(() => {
    if (!streaming) {
      setRendered(displayContent);
      return;
    }
    const t = setTimeout(() => setRendered(displayContent), 32);
    return () => clearTimeout(t);
  }, [displayContent, streaming]);

  const thinkingTrim = displayThinking.trim();
  const { realThinking } = partitionThinking(thinkingTrim);
  const hasRealThinking = Boolean(realThinking);
  const hasBody = Boolean(rendered && rendered.trim());
  const thinkingLines = hasRealThinking
    ? realThinking.split('\n').filter(Boolean).length
    : 0;

  // 有正文时强制收起；绝不因流式自动展开（默认收起）
  useEffect(() => {
    if (hasBody && hasRealThinking) {
      setThinkingExpanded(false);
    }
  }, [hasBody, hasRealThinking]);

  // 外部显式要求展开时同步一次
  useEffect(() => {
    if (thinkingOpen) setThinkingExpanded(true);
  }, [thinkingOpen]);

  const showThinkingPanel = hasRealThinking;

  return (
    <div className="stream-renderer" data-testid="stream-renderer">
      {showThinkingPanel && (
        <div
          className="stream-renderer__thinking"
          data-open={thinkingExpanded ? '1' : '0'}
          data-testid="thinking-panel"
        >
          <button
            type="button"
            className="stream-renderer__thinking-toggle"
            aria-expanded={thinkingExpanded}
            onClick={() => setThinkingExpanded((v) => !v)}
          >
            <span className="stream-renderer__thinking-caret" aria-hidden>
              {thinkingExpanded ? '▾' : '▸'}
            </span>
            <span className="stream-renderer__thinking-title">思考过程</span>
            {!thinkingExpanded && (
              <span className="stream-renderer__thinking-hint">
                {streaming && !hasBody
                  ? '生成中 · 点击展开'
                  : thinkingLines > 0
                    ? `${thinkingLines} 行 · 点击展开`
                    : '点击展开'}
              </span>
            )}
            {thinkingExpanded && (
              <span className="stream-renderer__thinking-hint">点击收起</span>
            )}
          </button>
          {thinkingExpanded && (
            <pre className="stream-renderer__thinking-body" data-testid="thinking-body">
              {realThinking}
            </pre>
          )}
        </div>
      )}
      <div
        className={`stream-renderer__body${
          collapseBody ? ' stream-renderer__body--collapsed' : ''
        }`}
      >
        {hasBody ? (
          <MarkdownRenderer content={rendered} />
        ) : streaming ? (
          <p className="stream-renderer__placeholder muted">
            {hasRealThinking
              ? '正在组织回答…'
              : /汇总|合并/.test(thinkingTrim)
                ? '汇总中…'
                : /评估/.test(thinkingTrim)
                  ? '评估中…'
                  : '执行中…'}
          </p>
        ) : null}
        {streaming && hasBody && (
          <span className="stream-renderer__cursor" aria-hidden>
            ▊
          </span>
        )}
      </div>
    </div>
  );
}
