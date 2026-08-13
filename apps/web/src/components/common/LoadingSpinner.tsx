import { cn } from '@/utils/cn';

interface LoadingSpinnerProps {
  fullScreen?: boolean;
  label?: string;
}

export function LoadingSpinner({ fullScreen, label = '加载中…' }: LoadingSpinnerProps) {
  return (
    <div
      className={cn('loading-spinner', fullScreen && 'loading-spinner--fullscreen')}
      role="status"
      aria-label={label}
    >
      <div className="spinner" />
      {label && <span className="loading-spinner__label">{label}</span>}
    </div>
  );
}
