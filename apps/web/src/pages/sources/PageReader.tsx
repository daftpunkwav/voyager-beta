/** 网页阅读器:剪藏正文 + 原文链接;agent 剪藏与用户剪藏同源展示。 */

import { Link, useNavigate, useParams } from 'react-router-dom';
import { useRemovePage, useSetPageMeta, useWebPage } from '@/hooks/useSources';
import { useUIStore } from '@/stores/uiStore';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
import { TagEditor } from './TagEditor';

export function PageReader() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: page, isLoading, isError, error, refetch } = useWebPage(id);
  const removePage = useRemovePage();
  const setMeta = useSetPageMeta();
  const addToast = useUIStore((s) => s.addToast);

  if (isLoading) {
    return <div className="reader-state"><LoadingSpinner label="加载网页中…" /></div>;
  }
  if (isError || !page) {
    return (
      <div className="reader-state">
        <EmptyState
          title="无法加载网页"
          description={error instanceof Error ? error.message : '剪藏不存在或服务不可用'}
          icon={EmptyStateIcons.library}
          action={<button type="button" className="btn btn-ghost" onClick={() => void refetch()}>重试</button>}
        />
      </div>
    );
  }

  return (
    <div className="page-reader">
      <header className="doc-reader__head">
        <Link to="/sources" className="doc-reader__back" aria-label="返回资源库">←</Link>
        <div className="doc-reader__meta">
          <h1>{page.title}</h1>
          <p className="muted small">
            {page.domain || '手动录入'}
            {page.meta?.chars ? ` · ${page.meta.chars} 字` : ''}
          </p>
          <TagEditor
            tags={page.tags ?? []}
            onChange={(tags) =>
              setMeta.mutate(
                { pageId: page.id, meta: { tags } },
                { onError: (e) => addToast({ type: 'error', message: e instanceof Error ? e.message : '标签保存失败' }) },
              )
            }
          />
        </div>
        <div className="doc-reader__actions">
          {page.url && (
            <a className="btn glass-card glass-card--control liquid-glass--pill liquid-glass--interactive" href={page.url} target="_blank" rel="noreferrer">
              查看原文
            </a>
          )}
          <button
            type="button"
            className="icon-btn"
            aria-label="删除剪藏"
            onClick={() => {
              if (!window.confirm(`删除剪藏「${page.title}」?此操作不可撤销。`)) return;
              removePage.mutate(page.id, {
                onSuccess: () => {
                  addToast({ type: 'success', message: '剪藏已删除' });
                  navigate('/sources');
                },
                onError: (e) => addToast({ type: 'error', message: e instanceof Error ? e.message : '删除失败' }),
              });
            }}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={16} height={16}>
              <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
            </svg>
          </button>
        </div>
      </header>
      <article className="page-reader__content">
        <MarkdownRenderer content={page.content} />
      </article>
    </div>
  );
}
