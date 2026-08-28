import { NavIcons } from '@/components/icons/NavIcons';

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: React.ReactNode;
  icon?: React.ReactNode;
  /** 离线/加载失败的统一主操作;与 action 同时传入时以 action 为准。 */
  onRetry?: () => void;
  retryLabel?: string;
}

/** 通用空/错误状态:居中图标+标题+描述+主操作。图标与侧栏 NavIcons 同源。 */
export function EmptyState({
  title,
  description,
  action,
  icon,
  onRetry,
  retryLabel = '重试',
}: EmptyStateProps) {
  const actionNode =
    action ??
    (onRetry ? (
      <button type="button" className="btn btn-primary" onClick={onRetry}>
        {retryLabel}
      </button>
    ) : null);

  return (
    <div className="empty-state" role="status">
      <div className="empty-state__icon" aria-hidden>
        {icon ?? EmptyStateIcons.inbox}
      </div>
      <h3 className="empty-state__title">{title}</h3>
      {description && <p className="empty-state__desc">{description}</p>}
      {actionNode && <div className="empty-state__action">{actionNode}</div>}
    </div>
  );
}

const ICON = { width: 30, height: 30 } as const;

export const EmptyStateIcons = {
  inbox: <NavIcons.notes {...ICON} />,
  team: <NavIcons.team {...ICON} />,
  graph: <NavIcons.graph {...ICON} />,
  settings: <NavIcons.settings {...ICON} />,
  activity: <NavIcons.activity {...ICON} />,
  usage: <NavIcons.usage {...ICON} />,
  health: <NavIcons.health {...ICON} />,
  library: <NavIcons.sources {...ICON} />,
  warning: (
    <svg
      viewBox="0 0 24 24"
      width={30}
      height={30}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </svg>
  ),
} as const;
