import { useEffect, useState } from 'react';
import type { Toast } from '@/stores/uiStore';
import { useUIStore } from '@/stores/uiStore';
import { describeError } from '@/utils/errorCodes';

/** 单条 Toast：到点先播消失动画（toast-out），动画结束才真正移除 */
function ToastItem({
  toast,
  onRemove,
}: {
  toast: Toast;
  onRemove: (id: string) => void;
}) {
  const [leaving, setLeaving] = useState(false);
  const duration = toast.duration ?? 3000;

  useEffect(() => {
    const t = setTimeout(() => setLeaving(true), duration);
    return () => clearTimeout(t);
  }, [duration]);

  const desc = toast.code ? describeError(toast.code) : null;
  const title = desc?.title ?? toast.message;

  return (
    <div
      className={`toast toast--${toast.type}${leaving ? ' toast--leaving' : ''}`}
      role="alert"
      onAnimationEnd={() => {
        if (leaving) onRemove(toast.id);
      }}
    >
      <div className="toast__body">
        <div className="toast__row">
          {toast.code && (
            <span className="toast-code" data-testid="toast-code">
              [{toast.code}]
            </span>
          )}
          <span className="toast-title">{title}</span>
        </div>
        {desc?.hint && <span className="toast-hint">{desc.hint}</span>}
      </div>
      <button
        type="button"
        className="toast__close"
        onClick={() => onRemove(toast.id)}
        aria-label="关闭"
      >
        ×
      </button>
    </div>
  );
}

export function ToastContainer() {
  const toasts = useUIStore((s) => s.toasts);
  const removeToast = useUIStore((s) => s.removeToast);

  if (toasts.length === 0) return null;

  return (
    <div className="toast-container" aria-live="polite" role="alert">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onRemove={removeToast} />
      ))}
    </div>
  );
}
