// @ts-nocheck — 迁移期:上游迁入的代码,字段重命名由 legacyApi 边界归一化,新 page / hook 仍按 strict 写(见各文件顶部注释)。
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useGraph } from '@/hooks/useGraph';
import { useGraphStore } from '@/stores/graphStore';
import type { GraphViewMode } from '@/stores/graphStore';
import { useUIStore } from '@/stores/uiStore';
import { UniverseGraphView } from '@/components/graph/UniverseGraphView';
import { GraphControls, getSimilarNodes } from '@/components/graph/GraphControls';
import { GraphGuidePanel } from '@/components/graph/GraphGuidePanel';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { formatNumber, REPO_AVATAR_GRADIENTS, splitRepoName } from '@/utils/format';
import { categoryLabel } from '@/utils/labels';
import { getApi } from '@/api/client';
import type { GraphEdge, GraphNode } from '@/api/types';
import {
  OVERVIEW_INNER_GLASS,
  OVERVIEW_OUTER_GLASS,
} from '@/constants/overviewGlass';

const SIMILAR_PREVIEW_COUNT = 3;

/** 展示形态：分类聚合已移除（信息密度差且与列表/图例重复） */
const VIEW_MODES: { id: GraphViewMode; label: string }[] = [
  { id: 'force', label: '宇宙图' },
  { id: 'list', label: '列表' },
];

export function GraphPage() {
  const { data, isLoading, isError, error, refetch } = useGraph();
  const crossQ = useQuery({
    queryKey: ['graph-cross-edges'],
    queryFn: () => getApi().getCrossEdges(),
    staleTime: 60_000,
  });
  const recommendQ = useQuery({
    queryKey: ['graph-recommend-edges'],
    queryFn: () => getApi().getRecommendEdges(),
    staleTime: 60_000,
  });
  const containerRef = useRef<HTMLDivElement>(null);
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchSelected, setBatchSelected] = useState<Set<string>>(new Set());
  const [cameraResetTick, setCameraResetTick] = useState(0);
  const [similarPage, setSimilarPage] = useState(0);
  const selectedNodeId = useGraphStore((s) => s.selectedNodeId);
  const selectNode = useGraphStore((s) => s.selectNode);
  const highlightNode = useGraphStore((s) => s.highlightNode);
  const searchQuery = useGraphStore((s) => s.searchQuery);
  const categoryFilter = useGraphStore((s) => s.categoryFilter);
  const edgeTypeFilter = useGraphStore((s) => s.edgeTypeFilter);
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
    onSuccess: (res) => {
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

  const mergedData = useMemo(() => {
    if (!data) return { nodes: [] as GraphNode[], edges: [] as GraphEdge[] };
    const cross = (crossQ.data?.data?.edges || []) as unknown as GraphEdge[];
    const recommend = (recommendQ.data?.data?.edges || []) as unknown as GraphEdge[];
    const edges: GraphEdge[] = [
      ...data.edges.map((e) => ({ ...e, edge_type: e.edge_type || 'similarity' })),
      ...cross.map((e) => ({
        ...e,
        similarity: e.similarity ?? 1,
        edge_type: e.edge_type || e.relation || 'cross_http',
      })),
      ...recommend.map((e) => ({
        ...e,
        similarity: e.similarity ?? 1,
        edge_type: e.edge_type || e.relation || 'recommend_learn',
      })),
    ];
    return { nodes: data.nodes, edges };
  }, [data, crossQ.data, recommendQ.data]);

  const filteredData = useMemo(() => {
    let nodes = mergedData.nodes;
    if (categoryFilter) {
      nodes = nodes.filter((n) => n.category_id === categoryFilter);
    }
    const ids = new Set(nodes.map((n) => n.id));
    let edges = mergedData.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    if (edgeTypeFilter) {
      edges = edges.filter((e) => (e.edge_type || 'similarity') === edgeTypeFilter);
    }
    return { nodes, edges };
  }, [mergedData, categoryFilter, edgeTypeFilter]);

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
      ? `https://github.com/${selectedRepo.owner}/${selectedRepo.repo}`
      : null;

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
        <header className="page-scaffold__head">
          <div>
            <h1>网络图谱</h1>
            <p className="page-scaffold__subtitle">项目关系、相似度与推荐边</p>
          </div>
        </header>
        <div className="page-scaffold__state">
          <EmptyState
            title="无法加载图谱"
            description={error instanceof Error ? error.message : '请检查后端服务后重试'}
            action={
              <button type="button" className="btn btn-primary" onClick={() => void refetch()}>
                重试
              </button>
            }
          />
        </div>
      </div>
    );
  }

  if ((data?.nodes.length ?? 0) < 2) {
    return (
      <div className="graph-page-shell page-scaffold">
        <header className="page-scaffold__head">
          <div>
            <h1>网络图谱</h1>
            <p className="page-scaffold__subtitle">项目关系、相似度与推荐边</p>
          </div>
        </header>
        <div className="page-scaffold__state">
          <EmptyState title="节点不足" description="至少需要 2 个项目才能生成关系图谱" />
        </div>
      </div>
    );
  }

  const batchSlot = (
    <>
      <div className="graph-batch-actions">
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
            <span>选择项目批量建索引</span>
            <button
              type="button"
              className="graph-batch-panel__close"
              onClick={() => setBatchOpen(false)}
            >
              ✕
            </button>
          </div>
          <div className="graph-batch-panel__list">
            {filteredData.nodes.map((n) => (
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
                setBatchSelected(new Set(filteredData.nodes.map((n) => n.id)))
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
              onNodeDoubleClick={(n) => navigate(`/graph/projects/${n.id}`)}
            />
          )}

          {viewMode === 'list' && (
            <div className="graph-list-view">
              <div className="graph-list-view__head">
                <h2>项目列表</h2>
                <span>{filteredData.nodes.length} 个项目</span>
              </div>
              {filteredData.nodes.map((n, idx) => {
                const similar = getSimilarNodes(filteredData, n.id).slice(0, 3);
                return (
                  <button
                    key={n.id}
                    type="button"
                    className={`graph-list-item${selectedNodeId === n.id ? ' is-selected' : ''}`}
                    onClick={() => selectNode(n.id)}
                    onDoubleClick={() => navigate(`/graph/projects/${n.id}`)}
                  >
                    <div
                      className="graph-list-avatar"
                      style={{
                        background: REPO_AVATAR_GRADIENTS[idx % REPO_AVATAR_GRADIENTS.length],
                      }}
                    >
                      {(splitRepoName(n.name).repo[0] ?? 'P').toUpperCase()}
                    </div>
                    <div className="graph-list-body">
                      <div className="graph-list-name">{n.name}</div>
                      <div className="graph-list-meta">
                        <span>{categoryLabel(n.category_id)}</span>
                        <span>·</span>
                        <span>{formatNumber(n.stars)} ★</span>
                        {n.language && (
                          <>
                            <span>·</span>
                            <span>{n.language}</span>
                          </>
                        )}
                        {similar.length > 0 && (
                          <>
                            <span>·</span>
                            <span className="graph-list-similar">
                              相似：
                              {similar.map((s) => splitRepoName(s.node.name).repo).join('、')}
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                    <div
                      className="graph-list-action"
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/graph/projects/${n.id}`);
                      }}
                    >
                      代码图谱 →
                    </div>
                  </button>
                );
              })}
            </div>
          )}

          {selectedNode && (
            <div className={`node-detail ${OVERVIEW_OUTER_GLASS}`}>
              <div className="node-detail-head">
                <div className="node-avatar" style={{ background: REPO_AVATAR_GRADIENTS[0] }}>
                  {(selectedRepo?.repo[0] ?? 'P').toUpperCase()}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="node-meta-name" title={selectedNode.name}>
                    {selectedRepo?.repo || selectedNode.name}
                  </div>
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
                  {similarNodes.length > 0 && (
                    <div className="node-detail-section node-detail-section--similar">
                      <div className="detail-label">相似项目</div>
                      <div className="similar-list">
                        {visibleSimilarNodes.map(({ node, similarity }) => {
                          const { owner, repo } = splitRepoName(node.name);
                          const githubUrl =
                            owner && repo ? `https://github.com/${owner}/${repo}` : null;
                          return (
                            <div
                              key={node.id}
                              className={`similar-item ${OVERVIEW_INNER_GLASS}`}
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
                                <span className="similar-owner">{owner || '—'}</span>
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
                  <div className="detail-actions">
                    <button
                      type="button"
                      className="btn btn-primary btn-block"
                      onClick={() => navigate(`/graph/projects/${selectedNode.id}`)}
                    >
                      打开代码图谱
                    </button>
                    <button
                      type="button"
                      className="btn btn--secondary btn-block"
                      onClick={() => navigate(`/projects/${selectedNode.id}`)}
                    >
                      项目详情
                    </button>
                  </div>
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
