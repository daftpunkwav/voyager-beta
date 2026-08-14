/** 统一降级态(§7.10):错误码 + 说明 + 处置建议 + 重试。 */

interface DegradedProps {
  code: string;
  message: string;
  hint?: string;
  onRetry?: () => void;
}

export function Degraded({ code, message, hint, onRetry }: DegradedProps) {
  return (
    <div className="degraded" role="alert">
      <div className="degraded__code mono">{code}</div>
      <div className="degraded__message">{message}</div>
      {hint ? <div className="degraded__hint small muted">{hint}</div> : null}
      {onRetry ? (
        <button type="button" className="btn" onClick={onRetry}>
          重试
        </button>
      ) : null}
    </div>
  );
}
