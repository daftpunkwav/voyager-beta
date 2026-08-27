import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  useCategories,
  useDeleteProject,
  useProjects,
  useProjectStats,
  useTags,
  useUpdateProgress,
} from '@/hooks/useProjects';
import { useProjectStore } from '@/stores/projectStore';
import { useUIStore } from '@/stores/uiStore';
import { FilterBar, useProjectLanguages } from '@/components/project/FilterBar';
import { ProjectTable } from '@/components/project/ProjectTable';
import { ImportStarsDrawer } from '@/components/project/ImportStarsDrawer';
import { ImportUrlsModal } from '@/components/project/ImportUrlsModal';
import { CategoryTagManager } from '@/components/project/CategoryTagManager';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { formatNumber } from '@/utils/format';
import {
  PROJECTS_OUTER_GLASS_OVERVIEW,
} from '@/constants/projectsGlass';

const STAT_ICONS = {
  total: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={16} height={16}>
      <path d="M3 7l9-4 9 4v10l-9 4-9-4V7z" />
      <path d="M3 7l9 4 9-4" />
    </svg>
  ),
  mastered: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={16} height={16}>
      <path d="M20 6L9 17l-5-5" />
    </svg>
  ),
  learning: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={16} height={16}>
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
    </svg>
  ),
  none: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={16} height={16}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  ),
};

export function ProjectsPage() {
  const { data, isLoading, isError, error, refetch } = useProjects();
  const { data: categories = [] } = useCategories();
  const { data: tags = [] } = useTags();
  const { data: stats } = useProjectStats();
  const page = useProjectStore((s) => s.page);
  const pageSize = useProjectStore((s) => s.pageSize);
  const setPage = useProjectStore((s) => s.setPage);
  const search = useProjectStore((s) => s.search);
  const selectedIds = useProjectStore((s) => s.selectedIds);
  const clearSelected = useProjectStore((s) => s.clearSelected);
  const deleteMutation = useDeleteProject();
  const updateProgress = useUpdateProgress();
  const addToast = useUIStore((s) => s.addToast);
  const [starsOpen, setStarsOpen] = useState(false);
  const [urlsOpen, setUrlsOpen] = useState(false);
  const [mgrOpen, setMgrOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [bulkPending, setBulkPending] = useState(false);
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const q = searchParams.get('q');
    if (q) useProjectStore.getState().setSearch(q);
    if (searchParams.get('import') === 'stars') setStarsOpen(true);
  }, [searchParams]);

  const total = data?.total ?? 0;
  const totalPages = data ? Math.ceil(data.total / pageSize) : 1;
  const byP = stats?.by_progress;

  const languages = useProjectLanguages(data?.items ?? []);

  const subtitle = useMemo(() => {
    const parts: string[] = [];
    if (search) parts.push(`"${search}"`);
    const tail = parts.length ? ` · 已筛选 ${parts.join(' · ')}` : '';
    return `${total} 个项目 · 最后同步于 ${new Date().toLocaleDateString('zh-CN')}${tail}`;
  }, [total, search]);

  const handleBulkDelete = async () => {
    if (selectedIds.length === 0) return;
    setBulkPending(true);
    let succeeded = 0;
    let failed = 0;
    for (const id of selectedIds) {
      try {
        await deleteMutation.mutateAsync(id);
        succeeded += 1;
      } catch {
        failed += 1;
      }
    }
    setBulkPending(false);
    setConfirmDelete(false);
    if (failed === 0) {
      addToast({ type: 'success', message: `已删除 ${succeeded} 个项目` });
    } else {
      addToast({
        type: failed === selectedIds.length ? 'error' : 'warning',
        message: `删除完成：成功 ${succeeded} / 失败 ${failed}`,
      });
    }
    clearSelected();
  };

  const handleBulkMarkLearning = async () => {
    if (selectedIds.length === 0) return;
    setBulkPending(true);
    let succeeded = 0;
    let failed = 0;
    for (const id of selectedIds) {
      try {
        await updateProgress.mutateAsync({ id, progress: 'learning' });
        succeeded += 1;
      } catch {
        failed += 1;
      }
    }
    setBulkPending(false);
    addToast({
      type: failed === 0 ? 'success' : 'warning',
      message: `已标记 ${succeeded} 个项目为学习中${failed > 0 ? `，${failed} 个失败` : ''}`,
    });
    clearSelected();
  };

  // 首次加载/失败时不渲染残缺页面壳(标题+筛选栏+悬空小卡片),
  // 与其它页面统一:居中加载指示或错误态 + 重试。
  if (isLoading) {
    return (
      <div className="page-scaffold projects-page">
        <div className="page-scaffold__state">
          <LoadingSpinner label="加载项目库中…" />
        </div>
      </div>
    );
  }
  if (isError) {
    return (
      <div className="page-scaffold projects-page">
        <div className="page-scaffold__state">
          <EmptyState
            title="无法加载项目库"
            description={error instanceof Error ? error.message : '请检查后端服务后重试'}
            icon={EmptyStateIcons.library}
            action={
              <button type="button" className="btn btn-ghost" onClick={() => void refetch()}>
                重试
              </button>
            }
          />
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>我的项目库</h1>
          <p className="subtitle">{subtitle}</p>
        </div>
        <div className="actions">
          <button
            type="button"
            className="btn glass-card glass-card--control liquid-glass--pill liquid-glass--interactive"
            onClick={() => setMgrOpen(true)}
          >
            分类/标签
          </button>
          <button
            type="button"
            className="btn glass-card glass-card--control liquid-glass--pill liquid-glass--interactive"
            data-testid="import-stars-btn"
            onClick={() => setStarsOpen(true)}
          >
            <span className="gh-dot" />
            GitHub 同步
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => setUrlsOpen(true)}
          >
            导入项目
          </button>
        </div>
      </div>

      {stats && (
        <section className="stat-grid" data-testid="stats-cards">
          <article className={`stat-card ${PROJECTS_OUTER_GLASS_OVERVIEW}`}>
            <div className="stat-icon">{STAT_ICONS.total}</div>
            <div className="stat-label">总项目数</div>
            <div className="stat-value">{stats.total}</div>
            <div className="stat-delta" style={{ color: 'var(--text-500)' }}>
              活跃库
            </div>
          </article>
          <article className={`stat-card stat-green ${PROJECTS_OUTER_GLASS_OVERVIEW}`}>
            <div className="stat-icon">{STAT_ICONS.mastered}</div>
            <div className="stat-label">已掌握</div>
            <div className="stat-value">{byP?.mastered ?? 0}</div>
            <div className="stat-delta">
              {stats.total ? Math.round(((byP?.mastered ?? 0) / stats.total) * 100) : 0}% · 占比
            </div>
          </article>
          <article className={`stat-card stat-orange ${PROJECTS_OUTER_GLASS_OVERVIEW}`}>
            <div className="stat-icon">{STAT_ICONS.learning}</div>
            <div className="stat-label">学习中</div>
            <div className="stat-value">{byP?.learning ?? 0}</div>
            <div className="stat-delta">
              {stats.total ? Math.round(((byP?.learning ?? 0) / stats.total) * 100) : 0}% · 占比
            </div>
          </article>
          <article className={`stat-card stat-purple ${PROJECTS_OUTER_GLASS_OVERVIEW}`}>
            <div className="stat-icon">{STAT_ICONS.none}</div>
            <div className="stat-label">待开始</div>
            <div className="stat-value">{byP?.none ?? 0}</div>
            <div className="stat-delta" style={{ color: 'var(--text-500)' }}>
              {stats.total ? Math.round(((byP?.none ?? 0) / stats.total) * 100) : 0}% · 占比
            </div>
          </article>
        </section>
      )}

      <FilterBar categories={categories} tags={tags} languages={languages} />

      {selectedIds.length > 0 && (
        <div className="bulk-bar" role="region" aria-label="批量操作" data-testid="bulk-bar">
          <span className="bulk-bar__count">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={14} height={14}>
              <path d="M20 6L9 17l-5-5" />
            </svg>
            已选 <strong>{selectedIds.length}</strong> 个项目
          </span>
          <div className="bulk-bar__actions">
            <button
              type="button"
              className="bulk-bar__btn"
              onClick={() => void handleBulkMarkLearning()}
              disabled={bulkPending}
              data-testid="bulk-mark-learning-btn"
            >
              标记学习中
            </button>
            <button
              type="button"
              className="bulk-bar__btn bulk-bar__btn--danger"
              onClick={() => setConfirmDelete(true)}
              disabled={bulkPending}
              data-testid="bulk-delete-btn"
            >
              删除选中
            </button>
            <button
              type="button"
              className="bulk-bar__btn"
              onClick={clearSelected}
              disabled={bulkPending}
              data-testid="bulk-clear-btn"
            >
              清除选择
            </button>
          </div>
        </div>
      )}

      <ProjectTable
        projects={data?.items ?? []}
        tags={tags}
        categories={categories}
        onImportClick={() => setStarsOpen(true)}
      />
      {data && data.items.length > 0 && (
        <div className="pagination">
          <span className="info">
            第 {page} / {totalPages} 页 · 共 {formatNumber(data.total)} 项
          </span>
          <div className="pages">
            <button
              type="button"
              className="page-btn"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
              aria-label="上一页"
            >
              ‹
            </button>
            <button type="button" className="page-btn active" aria-current="page">
              {page}
            </button>
            <button
              type="button"
              className="page-btn"
              disabled={page >= totalPages}
              onClick={() => setPage(page + 1)}
              aria-label="下一页"
            >
              ›
            </button>
          </div>
        </div>
      )}

      <ImportStarsDrawer open={starsOpen} onClose={() => setStarsOpen(false)} />
      <ImportUrlsModal open={urlsOpen} onClose={() => setUrlsOpen(false)} />
      <CategoryTagManager
        open={mgrOpen}
        onClose={() => setMgrOpen(false)}
        categories={categories}
        tags={tags}
      />

      <ConfirmDialog
        open={confirmDelete}
        title={`删除 ${selectedIds.length} 个项目？`}
        message="项目将从你的项目库中移除，相关笔记会保留但失去关联。此操作不可撤销。"
        confirmLabel="确认删除"
        cancelLabel="取消"
        danger
        onConfirm={() => void handleBulkDelete()}
        onCancel={() => setConfirmDelete(false)}
      />
    </>
  );
}
