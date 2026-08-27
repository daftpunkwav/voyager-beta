/** 仓库卡片:名称/描述/stars/语言/分类/标签 + 状态徽标与克隆进度条。 */

import type { CloneProgress, RepoSummary } from './sourcesStore';

const PROGRESS_LABELS: Record<string, string> = {
  none: '未学',
  learning: '在学',
  done: '已学',
};

export function RepoCard({
  repo,
  progress,
  onOpen,
}: {
  repo: RepoSummary;
  progress?: CloneProgress;
  onOpen: () => void;
}) {
  return (
    <button type="button" className={`repo-card repo-card--${repo.status}`} onClick={onOpen}>
      <div className="repo-card__head">
        <span className="repo-card__name">
          {repo.owner}/{repo.name}
        </span>
        <StatusBadge repo={repo} />
      </div>
      {repo.description ? (
        <div className="repo-card__desc small muted">{repo.description}</div>
      ) : null}
      <div className="repo-card__meta small muted">
        {repo.stars > 0 ? <span>★ {repo.stars}</span> : null}
        {repo.language ? <span>{repo.language}</span> : null}
        {repo.category ? <span className="repo-card__cat">{repo.category}</span> : null}
        {repo.progress !== 'none' ? <span>{PROGRESS_LABELS[repo.progress] ?? repo.progress}</span> : null}
      </div>
      {repo.tags.length > 0 ? (
        <div className="repo-card__tags">
          {repo.tags.map((t) => (
            <span key={t} className="tag-chip">
              {t}
            </span>
          ))}
        </div>
      ) : null}
      {repo.status === 'importing' && progress ? (
        <div className="chat-card__bar" title={progress.stage}>
          <div
            className="chat-card__fill"
            style={{ width: `${Math.round(progress.progress * 100)}%` }}
          />
        </div>
      ) : null}
    </button>
  );
}

function StatusBadge({ repo }: { repo: RepoSummary }) {
  if (repo.status === 'importing') {
    return <span className="setting-badge setting-badge--none">导入中…</span>;
  }
  if (repo.status === 'failed') {
    return (
      <span className="setting-badge repo-badge--failed" title={repo.error}>
        失败
      </span>
    );
  }
  return <span className="setting-badge setting-badge--ok">就绪</span>;
}
