/** 卡片外壳:标题 + 跳转 + 内容区(错误态统一复用 shell/Degraded,坑 3)。 */

import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Degraded } from '@/shell/Degraded';

export function CardShell({
  title,
  to,
  error,
  onRetry,
  loading,
  children,
}: {
  title: string;
  to: string;
  error?: { code: string; message: string };
  onRetry?: () => void;
  loading?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="overview-card usage-card">
      <div className="overview-card__head">
        <Link to={to} className="overview-card__title">{title}</Link>
      </div>
      {error ? (
        <Degraded
          code={error.code}
          message={error.message}
          hint="仅此卡片降级,其余不受影响"
          onRetry={onRetry}
        />
      ) : loading ? (
        <div className="loading-spinner overview-card__loading">
          <div className="spinner" />
        </div>
      ) : (
        children
      )}
    </div>
  );
}
