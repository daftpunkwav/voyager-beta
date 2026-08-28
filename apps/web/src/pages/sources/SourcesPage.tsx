/** 资源库页:统一资源流(kind 筛选)+ 五合一导入中心。
 *
 * 「仓库」面板复用页面内既有的 ProjectsPage(repo 表格/筛选/批量,页面私有组件
 * 同目录复用合法);全部/文档/网页走跨类型 list_sources 卡片流。
 */

import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useSourceEvents, useSourceStream } from '@/hooks/useSources';
import { useProjectStore } from '@/stores/projectStore';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { BACKEND_UNREACHABLE } from '@/utils/errors';
import { ProjectsPage } from './ProjectsPage';
import { ImportCenter, type ImportTab } from './ImportCenter';
import { SourceCard } from './SourceCard';

type KindTab = '' | 'repo' | 'doc' | 'web';

const TABS: { key: KindTab; label: string }[] = [
  { key: '', label: '全部' },
  { key: 'repo', label: '仓库' },
  { key: 'doc', label: '文档' },
  { key: 'web', label: '网页' },
];

export function SourcesPage() {
  const [tab, setTab] = useState<KindTab>('');
  const [importOpen, setImportOpen] = useState(false);
  const [importTab, setImportTab] = useState<ImportTab>('files');
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const q = searchParams.get('q');
    if (q) useProjectStore.getState().setSearch(q);
  }, [searchParams]);

  const { data: items, isLoading, isError, error, refetch } = useSourceStream({
    kind: tab || undefined,
  });
  useSourceEvents();
  const search = useProjectStore((s) => s.search);
  const filtered = useMemo(
    () =>
      items?.filter((r) =>
        search ? r.title.toLowerCase().includes(search.toLowerCase()) : true,
      ) ?? [],
    [items, search],
  );

  const openImport = (t: ImportTab) => {
    setImportTab(t);
    setImportOpen(true);
  };

  // 仓库 tab:既有 repo 页全量承接(自带筛选/统计/批量操作)
  if (tab === 'repo') {
    return (
      <div className="page-scaffold sources-page">
        <div className="page-head">
          <KindTabs tab={tab} onChange={setTab} />
          <div className="actions">
            <button type="button" className="btn glass-card glass-card--control liquid-glass--pill liquid-glass--interactive" onClick={() => openImport('github')}>
              导入仓库
            </button>
          </div>
        </div>
        <ProjectsPage embedded />
        <ImportCenter open={importOpen} initialTab={importTab} onClose={() => setImportOpen(false)} />
      </div>
    );
  }

  return (
    <div className="page-scaffold sources-page">
      <div className="page-head">
        <KindTabs tab={tab} onChange={setTab} />
        <div className="actions">
          <button
            type="button"
            className="btn glass-card glass-card--control liquid-glass--pill liquid-glass--interactive"
            onClick={() => openImport('web')}
          >
            存网址
          </button>
          <button type="button" className="btn btn-primary" onClick={() => openImport('files')}>
            导入文档
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="page-scaffold__state">
          <LoadingSpinner label="加载资源中…" />
        </div>
      ) : isError ? (
        <div className="page-scaffold__state">
          <EmptyState
            title="无法加载资源库"
            description={error instanceof Error ? error.message : BACKEND_UNREACHABLE}
            icon={EmptyStateIcons.library}
            onRetry={() => void refetch()}
          />
        </div>
      ) : filtered.length === 0 ? (
        <div className="page-scaffold__state">
          <EmptyState
            title={search ? '没有匹配的资源' : '资料库还是空的'}
            icon={EmptyStateIcons.library}
            action={!search && (
              <button type="button" className="btn btn-primary" onClick={() => openImport('files')}>
                导入
              </button>
            )}
          />
        </div>
      ) : (
        <div className="source-grid" data-testid="source-grid">
          {filtered.map((item) => (
            <SourceCard key={`${item.kind}-${item.id}`} item={item} />
          ))}
        </div>
      )}

      <ImportCenter open={importOpen} initialTab={importTab} onClose={() => setImportOpen(false)} />
    </div>
  );
}

function KindTabs({ tab, onChange }: { tab: KindTab; onChange: (t: KindTab) => void }) {
  return (
    <nav className="kind-tabs" role="tablist" aria-label="资源类型">
      {TABS.map((t) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          aria-selected={tab === t.key}
          className={`kind-tab ${tab === t.key ? 'is-active' : ''}`}
          onClick={() => onChange(t.key)}
        >
          {t.label}
        </button>
      ))}
    </nav>
  );
}
