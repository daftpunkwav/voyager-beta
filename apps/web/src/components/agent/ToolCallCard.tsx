import { ActionResultCard } from '@/components/agent/ActionResultCard';
import { parseActionResult } from '@/utils/actionResult';

interface ToolCallCardProps {
  name: string;
  args: Record<string, unknown>;
  result?: unknown;
  /** 是否在工具行上方渲染 ActionResultCard（外层已汇总时可关） */
  showAction?: boolean;
}

function previewArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args ?? {});
  if (entries.length === 0) return '';
  // 优先展示路由/定位字段，避免 description/task 长文挤占首屏
  const priority = [
    'target_agent',
    'name',
    'project_id',
    'title',
    'category_name',
    'progress',
    'owner',
    'repo',
    'path',
    'query',
    'task',
    'reason',
    'description',
  ];
  const rank = (k: string) => {
    const i = priority.indexOf(k);
    return i === -1 ? priority.length + 1 : i;
  };
  const ordered = [...entries].sort(([a], [b]) => rank(a) - rank(b));
  const parts = ordered.slice(0, 3).map(([k, v]) => {
    const raw = typeof v === 'string' ? v : JSON.stringify(v);
    const short = raw.length > 36 ? `${raw.slice(0, 34)}…` : raw;
    return `${k}=${short}`;
  });
  const more = ordered.length > 3 ? ` +${ordered.length - 3}` : '';
  return parts.join(' · ') + more;
}

function formatBlock(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/** 工具调用：成功写操作优先结果卡；技术细节默认收起 */
export function ToolCallCard({
  name,
  args,
  result,
  showAction = true,
}: ToolCallCardProps) {
  const done = result !== undefined;
  const action = parseActionResult(result);
  const argPreview = previewArgs(args);

  return (
    <div className={`tool-call-block ${done ? 'is-done' : 'is-running'}`}>
      {showAction && action && <ActionResultCard result={result} toolName={name} />}
      <details className={`tool-call ${done ? 'is-done' : 'is-running'}`}>
        <summary className="tool-call__summary">
          <span className="tool-call__caret" aria-hidden>
            ▸
          </span>
          <span className="tool-call__dot" aria-hidden />
          <span className="tool-call__name">{name}</span>
          {action ? (
            <span className="tool-call__preview" title={action.summary}>
              {action.summary}
            </span>
          ) : (
            argPreview && (
              <span className="tool-call__preview" title={argPreview}>
                {argPreview}
              </span>
            )
          )}
          <span className="tool-call__status">{done ? '完成' : '调用中'}</span>
        </summary>
        <div className="tool-call__panel">
          <div className="tool-call__section">
            <span className="tool-call__k">参数</span>
            <pre className="tool-call__code">{formatBlock(args)}</pre>
          </div>
          {done && (
            <div className="tool-call__section">
              <span className="tool-call__k">结果</span>
              <pre className="tool-call__code">{formatBlock(result)}</pre>
            </div>
          )}
        </div>
      </details>
    </div>
  );
}
