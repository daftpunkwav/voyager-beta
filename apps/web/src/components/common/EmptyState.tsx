interface EmptyStateProps {
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="empty-state" role="status">
      <div className="empty-state__icon" aria-hidden>
        <svg viewBox="0 0 64 64" width={48} height={48} fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="10" y="18" width="44" height="34" rx="4" />
          <path d="M10 28h44" />
          <path d="M22 12l-6 6h12l-6-6z" strokeLinejoin="round" />
        </svg>
      </div>
      <h3 className="empty-state__title">{title}</h3>
      {description && <p className="empty-state__desc">{description}</p>}
      {action && <div className="empty-state__action">{action}</div>}
    </div>
  );
}
