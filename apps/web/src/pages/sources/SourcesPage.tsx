/** 资源库页:顶栏(导入/搜索/排序/分类)+ 卡片网格 + 详情抽屉;SSE 进度接线。 */

import { useEffect, useState } from 'react';
import { subscribe } from '@/bridge/stream';
import { Degraded } from '@/shell/Degraded';
import { useSourcesStore } from './sourcesStore';
import { RepoCard } from './RepoCard';
import { ImportDialog } from './ImportDialog';
import { RepoDetail } from './RepoDetail';

const STREAM_PATTERNS = [
  'task.progress',
  'task.completed',
  'task.failed',
  'source.added',
  'source.ready',
  'source.removed',
];

export function SourcesPage() {
  const { loading, error, init, sort, desc, category, categories, repos, setView, dispatch } =
    useSourcesStore();
  const progress = useSourcesStore((s) => s.progress);
  const [importing, setImporting] = useState(false);
  const [detailId, setDetailId] = useState<string | null>(null);

  useEffect(() => {
    void init();
  }, [init]);

  useEffect(
    () => subscribe(STREAM_PATTERNS, (ev) => dispatch(ev)),
    [dispatch],
  );

  if (error) {
    return (
      <Degraded
        code={error.code}
        message={`资源库服务不可用:${error.message}`}
        hint="其余页面不受影响"
        onRetry={() => void init()}
      />
    );
  }

  return (
    <section className="sources-page">
      <div className="sources-toolbar">
        <button type="button" className="btn btn-primary" onClick={() => setImporting((v) => !v)}>
          导入仓库
        </button>
        <span className="sources-toolbar__spacer" />
        <label className="small muted">
          排序
          <select
            className="setting-input"
            style={{ width: 'auto', marginLeft: 6 }}
            value={sort}
            onChange={(e) => setView({ sort: e.target.value as typeof sort })}
          >
            <option value="added">加入时间</option>
            <option value="name">名称</option>
            <option value="stars">stars</option>
            <option value="updated">更新时间</option>
          </select>
        </label>
        <button type="button" className="btn" onClick={() => setView({ desc: !desc })}>
          {desc ? '降序' : '升序'}
        </button>
        <label className="small muted">
          分类
          <select
            className="setting-input"
            style={{ width: 'auto', marginLeft: 6 }}
            value={category}
            onChange={(e) => setView({ category: e.target.value })}
          >
            <option value="">全部</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
      </div>

      {importing ? (
        <ImportDialog
          onDone={() => {
            setImporting(false);
          }}
        />
      ) : null}

      {loading ? (
        <div className="loading-spinner">
          <div className="spinner" />
        </div>
      ) : (
        <div className="sources-grid">
          {repos.length === 0 ? (
            <p className="muted small">还没有仓库;粘贴 GitHub 链接导入,或让 Lucien 帮你导入。</p>
          ) : null}
          {repos.map((r) => (
            <RepoCard
              key={r.id}
              repo={r}
              progress={progress[r.id]}
              onOpen={() => setDetailId(r.id)}
            />
          ))}
        </div>
      )}

      {detailId ? <RepoDetail repoId={detailId} onClose={() => setDetailId(null)} /> : null}
    </section>
  );
}
