/** 统一资源流卡片:kind 图标 + 状态徽章 + 元信息;点击按类型跳转阅读器。 */

import { Link } from 'react-router-dom';
import type { SourceSummary } from '@/hooks/useSources';

const KIND_META: Record<string, { label: string; icon: React.ReactNode }> = {
  repo: {
    label: '仓库',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={18} height={18}>
        <path d="M3 7l9-4 9 4v10l-9 4-9-4V7z" />
        <path d="M3 7l9 4 9-4" />
      </svg>
    ),
  },
  doc: {
    label: '文档',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={18} height={18}>
        <path d="M14 2H6a1 1 0 0 0-1 1v18a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V7z" />
        <path d="M14 2v5h5M9 13h6M9 17h6" />
      </svg>
    ),
  },
  web: {
    label: '网页',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={18} height={18}>
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18M12 3a15 15 0 0 1 0 18 15 15 0 0 1 0-18z" />
      </svg>
    ),
  },
};

const STATUS_META: Record<string, { label: string; cls: string }> = {
  importing: { label: '导入中', cls: 'is-busy' },
  parsing: { label: '解析中', cls: 'is-busy' },
  ready: { label: '就绪', cls: 'is-ok' },
  stored: { label: '已存档', cls: 'is-idle' },
  failed: { label: '失败', cls: 'is-fail' },
};

export function SourceCard({ item }: { item: SourceSummary }) {
  const meta = KIND_META[item.kind] ?? KIND_META.repo;
  const status = STATUS_META[item.status] ?? STATUS_META.ready;
  const href =
    item.kind === 'doc' ? `/sources/doc/${item.id}`
      : item.kind === 'web' ? `/sources/web/${item.id}`
        : `/sources/repo/${item.id}`;
  return (
    <Link to={href} className={`source-card glass-card glass-card--overview-outer source-card--${item.kind}`} data-testid={`source-card-${item.kind}`}>
      <div className="source-card__top">
        <span className={`source-card__kind source-card__kind--${item.kind}`}>{meta.icon}</span>
        <span className={`source-card__status ${status.cls}`}>{status.label}</span>
      </div>
      <h3 className="source-card__title">{item.title}</h3>
      {item.subtitle && <p className="source-card__subtitle">{item.subtitle}</p>}
      <div className="source-card__foot">
        {item.category && <span className="badge">{item.category}</span>}
        {item.tags.slice(0, 3).map((t) => (
          <span key={t} className="badge badge--tag">{t}</span>
        ))}
        <span className="source-card__time">
          {new Date((item.updated_ts || item.added_ts) * 1000).toLocaleDateString('zh-CN')}
        </span>
      </div>
    </Link>
  );
}
