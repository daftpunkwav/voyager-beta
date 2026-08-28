import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useGraph } from '@/hooks/useGraph';
import { useGraphStore } from '@/stores/graphStore';
import type { GraphViewMode } from '@/stores/graphStore';
import { useUIStore } from '@/stores/uiStore';
import { UniverseGraphView } from '@/components/graph/UniverseGraphView';
import { GraphControls, getSimilarNodes } from '@/components/graph/GraphControls';
import { GraphGuidePanel } from '@/components/graph/GraphGuidePanel';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { formatNumber, REPO_AVATAR_GRADIENTS, splitRepoName } from '@/utils/format';
import { getApi } from '@/api/client';
import { routes } from '@/utils/routes';
import { safeHttpUrl } from '@/utils/safeUrl';
import { BACKEND_UNREACHABLE } from '@/utils/errors';
import type { GraphNode } from '@/api/types';
// 玻璃层级 token(旧 OVERVIEW_OUTER_GLASS / OVERVIEW_INNER_GLASS 已统一至此)
import { GLASS_INNER, GLASS_OUTER } from '@/constants/glassTokens';

const SIMILAR_PREVIEW_COUNT = 3;

const KIND_LABELS: Record<string, string> = {
  repo: '仓库',
  doc: '文档',
  web: '网页',
};

/** 展示形态：分类聚合已移除（信息密度差且与列表/图例重复） */
const VIEW_MODES: { id: GraphViewMode; label: string }[] = [
  { id: 'force', label: '宇宙图' },
  { id: 'list', label: '列表' },
];

export function GraphPage() {
  const { data, isLoading, isError, error, refetch } = useGraph();
  const containerRef = useRef<HTMLDivElement>(null);
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchSelected, setBatchSelected] = useState<Set<string>>(new Set());
  const [cameraResetTick, setCameraResetTick] = useState(0);
  const [similarPage, setSimilarPage] = useState(0);
  const selectedNodeId = useGraphStore((s) => s.selectedNodeId);
  const selectNode = useGraphStore((s) => s.selectNode);
  const highlightNode = useGraphStore((s) => s.highlightNode);
  const searchQuery = useGraphStore((s) => s.searchQuery);
  const kindsFilter = useGraphStore((s) => s.kindsFilter);
  const edgeTypeFilter = useGraphStore((s) => s.edgeTypeFilter);
  const minSimilarity = useGraphStore((s) => s.minSimilarity);
  const viewModeRaw = useGraphStore((s) => s.viewMode);
  /** 废弃的 cluster/edges 归一到宇宙图或列表 */
  const viewMode: GraphViewMode = viewModeRaw === 'list' ? 'list' : 'force';
  const setViewMode = useGraphStore((s) => s.setViewMode);
  const leftPanelCollapsed = useGraphStore((s) => s.leftPanelCollapsed);
  const addToast = useUIStore((s) => s.addToast);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showUniverseChrome = viewMode === 'force';

  const batchIndex = useMutation({
    mutationFn: (ids: string[]) => getApi().batchIndexCodeGraph(ids, 'moderate'),
    // 显式标注旧 ApiResponse 信封(useMutation 对 TData=unknown 的推断会使 res 退化为 unknown)
    onSuccess: (res: { data: unknown }) => {
      const payload = res.data as {
        queued?: string[] | number;
        failed?: string[];
        items?: unknown[];
      };
      const queuedLen = Array.isArray(payload.queued)
        ? payload.queued.length
        : typeof payload.queued === 'number'
          ? payload.queued
          : (payload.items?.length ?? 0);
      const failedLen = Array.isArray(payload.failed) ? payload.failed.length : 0;
      addToast({
        type: failedLen === 0 ? 'success' : 'warning',
        message: `已入队 ${queuedLen} 个项目${failedLen ? `，${failedLen} 个失败` : ''}`,
      });
      setBatchOpen(false);
      setBatchSelected(new Set());
      void queryClient.invalidateQueries({ queryKey: ['graph-index-statuses'] });
    },
    onError: () => addToast({ type: 'error', message: '批量索引请求失败' }),
  });

  const analyzeL0 = useMutation({
    mutationFn: (kinds: string[]) => getApi().enqueueL0(kinds),
    onSuccess: () => {
      addToast({ type: 'success', message: 'L0 关联分析已入队，完成后图谱自动更新' });
      void queryClient.invalidateQueries({ queryKey: ['graph-index-statuses'] });
    },
    onError: (e) =>
      addToast({
        type: 'error',
        message: e instanceof Error ? e.message : '关联分析请求失败',
      }),
  });

  // L0 关联分析范围:未筛选=全部种类;筛选=选中种类
  const analyzeKinds = kindsFilter ? [...kindsFilter].sort() : ['repo', 'doc', 'web'];

  const filteredData = useMemo(() => {
    let nodes = data?.nodes ?? [];
    let edges = data?.edges ?? [];
    if (minSimilarity > 0) {
      edges = edges.filter((e) => e.similarity >= minSimilarity);
    }
    const ids = new Set(nodes.map((n) => n.id));
    edges = edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    if (edgeTypeFilter) {
      edges = edges.filter((e) => (e.edge_type || 'related') === edgeTypeFilter);
    }
    return { nodes, edges };
  }, [data, minSimilarity, edgeTypeFilter]);

  useEffect(() => {
    if (!searchQuery || !data) {
      highlightNode(null);
      return;
    }
    const q = searchQuery.toLowerCase();
    const match = data.nodes.find((n) => n.name.toLowerCase().includes(q));
    highlightNode(match?.id ?? null);
  }, [searchQuery, data, highlightNode]);

  const selectedNode: GraphNode | undefined = filteredData.nodes.find(
    (n) => n.id === selectedNodeId,
  );

  const similarNodes = selectedNode
    ? getSimilarNodes(filteredData, selectedNode.id)
    : [];

  useEffect(() => {
    setSimilarPage(0);
  }, [selectedNodeId]);

  /** 右侧详情栏高度与左侧信息栏对齐（收起左侧时保留上次展开高度） */
  useEffect(() => {
    const stage = containerRef.current;
    if (!stage) return;
    const toolbar = stage.querySelector('.graph-toolbar');
    if (!(toolbar instanceof HTMLElement)) return;

    const syncHeight = () => {
      if (toolbar.classList.contains('is-collapsed')) return;
      const h = Math.round(toolbar.getBoundingClientRect().height);
      if (h > 0) stage.style.setProperty('--graph-left-panel-h', `${h}px`);
    };

    syncHeight();
    const ro = new ResizeObserver(syncHeight);
    ro.observe(toolbar);
    return () => ro.disconnect();
  }, [viewMode, leftPanelCollapsed, batchOpen, isLoading, data?.nodes.length]);

  const similarPageCount = Math.max(1, Math.ceil(similarNodes.length / SIMILAR_PREVIEW_COUNT));
  const clampedSimilarPage = Math.min(similarPage, similarPageCount - 1);
  const visibleSimilarNodes = similarNodes.slice(
    clampedSimilarPage * SIMILAR_PREVIEW_COUNT,
    (clampedSimilarPage + 1) * SIMILAR_PREVIEW_COUNT,
  );
  const selectedRepo = selectedNode ? splitRepoName(selectedNode.name) : null;
  const selectedGithubUrl =
    selectedRepo?.owner && selectedRepo.repo
      ? safeHttpUrl(`https://github.com/${selectedRepo.owner}/${selectedRepo.repo}`)
      : undefined;

  if (isLoading) {
    return (
      <div className="graph-page-shell page-scaffold">
        <LoadingSpinner fullScreen label="加载图谱中…" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="graph-page-shell page-scaffold">
        <div className="page-scaffold__state">
          <EmptyState
            title="无法加载图谱"
            description={error instanceof Error ? error.message : BACKEND_UNREACHABLE}
            icon={EmptyStateIcons.graph}
            onRetry={() => void refetch()}
          />
        </div>
      </div>
    );
  }

  if ((data?.nodes.length ?? 0) < 2) {
    return (
      <div className="graph-page-shell page-scaffold">
        <div className="page-scaffold__state">
          <EmptyState
            title="图谱还是空的"
            description="先在资源库导入资源并打上标签，再运行「分析关联」生成 L0 关联图"
            icon={EmptyStateIcons.graph}
            action={
              <button
                type="button"
                className="btn btn-primary"
                disabled={analyzeL0.isPending}
                onClick={() => analyzeL0.mutate(analyzeKinds)}
              >
                {analyzeL0.isPending ? '提交中…' : '分析关联'}
              </button>
            }
          />
        </div>
      </div>
    );
  }

  /** 批量 L1 代码索引只对 repo 资源有意义 */
  const repoNodes = filteredData.nodes.filter((n) => !n.kind || n.kind === 'repo');

  const batchSlot = (
    <>
      <div className="graph-batch-actions">
        <button
          type="button"
          className="graph-batch-btn graph-batch-btn--inline"
          disabled={analyzeL0.isPending}
          onClick={() => analyzeL0.mutate(analyzeKinds)}
          title={`对当前选中的资源种类（${analyzeKinds.join(' / ')}）运行 L0 关联分析`}
        >
          {analyzeL0.isPending ? '分析中…' : '分析关联'}
        </button>
        <button
          type="button"
          className={`graph-batch-btn graph-batch-btn--inline${batchOpen ? ' is-active' : ''}`}
          onClick={() => setBatchOpen((v) => !v)}
        >
          批量索引
        </button>
        {viewMode === 'force' && (
          <button
            type="button"
            className="graph-batch-btn graph-batch-btn--inline"
            onClick={() => setCameraResetTick((n) => n + 1)}
            title="回到全图总览视角"
          >
            重置视角
          </button>
        )}
      </div>
      {batchOpen && (
        <div className="graph-batch-panel graph-batch-panel--inline glass-card glass-card--overview-inner">
          <div className="graph-batch-panel__head">
            <span>选择仓库批量建代码索引（L1）</span>
            <button
              type="button"
              className="graph-batch-panel__close"
              onClick={() => setBatchOpen(false)}
            >
              ✕
            </button>
          </div>
          <div className="graph-batch-panel__list">
            {repoNodes.map((n) => (
              <label key={n.id} className="graph-batch-item">
                <input
                  type="checkbox"
                  checked={batchSelected.has(n.id)}
                  onChange={(e) => {
                    const next = new Set(batchSelected);
                    if (e.target.checked) next.add(n.id);
                    else next.delete(n.id);
                    setBatchSelected(next);
                  }}
                />
                <span>{n.name}</span>
              </label>
            ))}
          </div>
          <div className="graph-batch-panel__footer">
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={batchSelected.size === 0 || batchIndex.isPending}
              onClick={() => batchIndex.mutate([...batchSelected])}
            >
              {batchIndex.isPending ? '提交中…' : `索引选中 (${batchSelected.size})`}
            </button>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() =>
                setBatchSelected(new Set(repoNodes.map((n) => n.id)))
              }
            >
              全选
            </button>
            <button type="button" className="btn btn-sm" onClick={() => setBatchSelected(new Set())}>
              清空
            </button>
          </div>
        </div>
      )}
    </>
  );

  return (
    <div className="graph-page-shell">
      <div className="graph-content">
        <div
          className={`graph-stage${showUniverseChrome ? ' graph-stage--universe' : ' graph-stage--list'}`}
          ref={containerRef}
        >
          <GraphControls
            showLayout={showUniverseChrome}
            viewModes={VIEW_MODES}
            viewMode={viewMode}
            onViewModeChange={setViewMode}
            batchSlot={batchSlot}
          />

          {viewMode === 'force' && (
            <UniverseGraphView
              data={filteredData}
              cameraResetTick={cameraResetTick}
              onNodeClick={(n) => selectNode(n.id)}
              onNodeDoubleClick={(n) =>
                navigate(
                  n.kind === 'doc' || n.kind === 'web'
                    ? routes.sourceOf(n.kind, n.resourceId ?? n.id)
                    : routes.codeGraph(n.resourceId ?? n.id),
                )
              }
            />
          )}

          {viewMode === 'list' && (
            <div className="graph-list-view">
              <div className="graph-list-view__head">
                <h2>资源列表</h2>
                <span>{filteredData.nodes.length} 个资源</span>
              </div>
              {filteredData.nodes.map((n, idx) => {
                const similar = getSimilarNodes(filteredData, n.id).slice(0, 3);
                const isRepo = !n.kind || n.kind === 'repo';
                return (
                  <button
                    key={n.id}
                    type="button"
                    className={`graph-list-item${selectedNodeId === n.id ? ' is-selected' : ''}`}
                    onClick={() => selectNode(n.id)}
                    onDoubleClick={() =>
                      navigate(routes.sourceOf(n.kind, n.resourceId ?? n.id))
                    }
                  >
                    <div
                      className="graph-list-avatar"
                      style={{
                        background: REPO_AVATAR_GRADIENTS[idx % REPO_AVATAR_GRADIENTS.length],
                      }}
                    >
                      {(n.name[0] ?? 'R').toUpperCase()}
                    </div>
                    <div className="graph-list-body">
                      <div className="graph-list-name">{n.name}</div>
                      <div className="graph-list-meta">
                        <span>{KIND_LABELS[n.kind ?? 'repo']}</span>
                        {n.category && (
                          <>
                            <span>·</span>
                            <span>{n.category}</span>
                          </>
                        )}
                        {isRepo && (
                          <>
                            <span>·</span>
                            <span>{formatNumber(n.stars)} ★</span>
                          </>
                        )}
                        {n.tags && n.tags.length > 0 && (
                          <>
                            <span>·</span>
                            <span>{n.tags.slice(0, 3).join(' / ')}</span>
                          </>
                        )}
                        {similar.length > 0 && (
                          <>
                            <span>·</span>
                            <span className="graph-list-similar">
                              关联：
                              {similar.map((s) => s.node.name).join('、')}
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                    {isRepo && (
                      <div
                        className="graph-list-action"
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(routes.codeGraph(n.resourceId ?? n.id));
                        }}
                      >
                        代码图谱 →
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          )}

          {selectedNode && (
            <div className={`node-detail ${GLASS_OUTER}`}>
              <div className="node-detail-head">
                <div className="node-avatar" style={{ background: REPO_AVATAR_GRADIENTS[0] }}>
                  {(selectedRepo?.repo[0] ?? selectedNode.name[0] ?? 'R').toUpperCase()}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="node-meta-name" title={selectedNode.name}>
                    {selectedRepo?.repo || selectedNode.name}
                  </div>
                  {selectedNode.kind && selectedNode.kind !== 'repo' && (
                    <div className="node-meta-kind">{KIND_LABELS[selectedNode.kind]}</div>
                  )}
                </div>
                <button
                  type="button"
                  className="node-detail-close"
                  title="关闭"
                  onClick={() => selectNode(null)}
                >
                  ✕
                </button>
              </div>
              <div className="node-detail-body">
                  {selectedNode.kind === 'doc' || selectedNode.kind === 'web' ? (
                    <>
                      <div className="node-detail-section">
                        <div className="detail-label">概览</div>
                        <div className="detail-row">
                          <span className="muted">类型</span>
                          <strong>{KIND_LABELS[selectedNode.kind]}</strong>
                        </div>
                        <div className="detail-row">
                          <span className="muted">分类</span>
                          <strong>{selectedNode.category || '—'}</strong>
                        </div>
                        <div className="detail-row">
                          <span className="muted">标签</span>
                          <strong>
                            {selectedNode.tags && selectedNode.tags.length > 0
                              ? selectedNode.tags.join('、')
                              : '—'}
                          </strong>
                        </div>
                      </div>
                      <div className="detail-actions">
                        <button
                          type="button"
                          className="btn btn-primary btn-block"
                          onClick={() =>
                            navigate(
                              routes.sourceOf(
                                selectedNode.kind,
                                selectedNode.resourceId ?? selectedNode.id,
                              ),
                            )
                          }
                        >
                          打开资源
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="node-detail-section">
                        <div className="detail-label">概览</div>
                        <div className="detail-row">
                          <span className="muted">所有者</span>
                          <strong className="detail-owner">{selectedRepo?.owner || '—'}</strong>
                        </div>
                        <div className="detail-row">
                          <span className="muted">GitHub</span>
                          {selectedGithubUrl ? (
                            <a
                              className="detail-github-link"
                              href={selectedGithubUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              title={selectedGithubUrl}
                            >
                              {`${selectedRepo?.owner}/${selectedRepo?.repo}`}
                            </a>
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </div>
                      </div>
                      <div className="detail-actions">
                        <button
                          type="button"
                          className="btn btn-primary btn-block"
                          onClick={() =>
                            navigate(routes.codeGraph(selectedNode.resourceId ?? selectedNode.id))
                          }
                        >
                          打开代码图谱
                        </button>
                        <button
                          type="button"
                          className="btn btn--secondary btn-block"
                          onClick={() =>
                            navigate(
                              routes.sourceRepo(selectedNode.resourceId ?? selectedNode.id),
                            )
                          }
                        >
                          项目详情
                        </button>
                      </div>
                    </>
                  )}
                  {similarNodes.length > 0 && (
                    <div className="node-detail-section node-detail-section--similar">
                      <div className="detail-label">关联资源</div>
                      <div className="similar-list">
                        {visibleSimilarNodes.map(({ node, similarity }) => {
                          const { owner, repo } = splitRepoName(node.name);
                          const githubUrl =
                            owner && repo
                              ? safeHttpUrl(`https://github.com/${owner}/${repo}`)
                              : undefined;
                          return (
                            <div
                              key={node.id}
                              className={`similar-item ${GLASS_INNER}`}
                            >
                              <button
                                type="button"
                                className="similar-item__main"
                                onClick={() => selectNode(node.id)}
                                title={node.name}
                              >
                                <span className="similar-name">{repo || node.name}</span>
                                <span className="similar-score">{similarity.toFixed(2)}</span>
                              </button>
                              <div className="similar-item__meta">
                                <span className="similar-owner">
                                  {KIND_LABELS[node.kind ?? 'repo']}
                                </span>
                                {githubUrl ? (
                                  <a
                                    className="similar-github"
                                    href={githubUrl}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    title={`在 GitHub 打开 ${owner}/${repo}`}
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    GitHub ↗
                                  </a>
                                ) : null}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                      {similarPageCount > 1 && (
                        <div className="similar-pager" role="navigation" aria-label="相似项目翻页">
                          <button
                            type="button"
                            className="similar-pager__btn"
                            disabled={clampedSimilarPage <= 0}
                            onClick={() => setSimilarPage((p) => Math.max(0, p - 1))}
                            title="上一页"
                          >
                            ‹
                          </button>
                          <span className="similar-pager__meta">
                            {clampedSimilarPage + 1} / {similarPageCount}
                          </span>
                          <button
                            type="button"
                            className="similar-pager__btn"
                            disabled={clampedSimilarPage >= similarPageCount - 1}
                            onClick={() =>
                              setSimilarPage((p) => Math.min(similarPageCount - 1, p + 1))
                            }
                            title="下一页"
                          >
                            ›
                          </button>
                        </div>
                      )}
                    </div>
                  )}
              </div>
            </div>
          )}

          <div className="graph-statusbar glass-card glass-card--overview-inner">
            <div>
              <span className="stat-row">
                <span className="stat-dot" />
                <span className="stat-mono">
                  {filteredData.nodes.length} 节点 / {filteredData.edges.length} 连线
                </span>
              </span>
            </div>
            <div className="export-actions">
              <button
                type="button"
                className="export-btn"
                onClick={() => addToast({ type: 'info', message: '导出功能即将上线' })}
              >
                导出
              </button>
            </div>
          </div>
        </div>
      </div>

      <GraphGuidePanel selectedNodeId={selectedNodeId} />
    </div>
  );
}
