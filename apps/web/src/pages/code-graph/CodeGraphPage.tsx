import { useMemo, useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { GraphScene, computeCameraTarget } from '@/components/graph-viz';
import type { CameraTarget, CodeGraphNode } from '@/components/graph-viz';
import { CodeGraphSidebar } from '@/components/code-graph/CodeGraphSidebar';
import { NodeDetailPanel } from '@/components/code-graph/NodeDetailPanel';
import { IndexStatusBar } from '@/components/code-graph/IndexStatusBar';
import { GraphGuidePanel } from '@/components/graph/GraphGuidePanel';
import { DisplaySettingsMenu } from '@/components/code-graph/DisplaySettingsMenu';
import { applyL1Layout, type L1LayoutMode } from '@/components/code-graph/l1Layout';
import {
  useCodeGraph,
  useIndexStatus,
  useTriggerIndex,
  useRefreshIndex,
  useDeleteIndex,
} from '@/hooks/useCodeGraph';
import { useCodeGraphStore } from '@/stores/codeGraphStore';
import { getApi } from '@/api/client';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { useUIStore } from '@/stores/uiStore';
import { rememberCodeGraphDetail } from './provider';
import {
  loadDisplaySettings,
  saveDisplaySettings,
  withStatusColorDisplay,
  type DisplaySettings,
} from '@/components/code-graph/density';
import { colorForStatus } from '@/components/code-graph/colors';

export function CodeGraphPage() {
  const { id } = useParams<{ id: string }>();

  const {
    showLabels,
    nodeBudget,
    selectedNode,
    searchQuery,
    nodeTypeFilter,
    edgeTypeFilter,
    showOnlyDead,
    colorByStatus,
    hideTests,
    hideEntryPoints,
    selectNode,
    setNodeBudget,
  } = useCodeGraphStore();

  const [display, setDisplay] = useState<DisplaySettings>(() =>
    loadDisplaySettings(),
  );
  const updateDisplay = useCallback((next: DisplaySettings) => {
    setDisplay(next);
    saveDisplaySettings(next);
  }, []);
  const effectiveDisplay = useMemo(
    () => (colorByStatus ? withStatusColorDisplay(display) : display),
    [colorByStatus, display],
  );

  const statusQ = useIndexStatus(id);
  const status = statusQ.data?.data;
  const ready = status?.status === 'READY';

  const addToast = useUIStore((s) => s.addToast);
  const onIndexOpError = (label: string) => (err: Error) => {
    addToast({ type: 'error', message: `${label}失败：${err.message || '请检查后端服务'}` });
  };
  const trigger = useTriggerIndex(id, { onError: onIndexOpError('触发索引') });
  const refresh = useRefreshIndex(id, { onError: onIndexOpError('刷新索引') });
  const delIndex = useDeleteIndex(id, { onError: onIndexOpError('删除索引') });

  const graphQ = useCodeGraph(id, { maxNodes: nodeBudget, enabled: Boolean(ready) });

  const projectQ = useQuery({
    queryKey: ['project', id],
    enabled: Boolean(id),
    queryFn: () => {
      if (!id) throw new Error('缺少项目 id');
      return getApi().getProject(id);
    },
  });

  const [cameraTarget, setCameraTarget] = useState<CameraTarget | null>(null);
  const [highlightedIds, setHighlightedIds] = useState<Set<number> | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [layoutMode, setLayoutMode] = useState<L1LayoutMode>('engine');

  const render = graphQ.data?.render;
  const filtered = useMemo(() => {
    if (!render) return null;
    let nodes: CodeGraphNode[] = render.nodes;
    if (nodeTypeFilter) {
      nodes = nodes.filter((n) => nodeTypeFilter.has(n.kind || n.label));
    }
    if (showOnlyDead) nodes = nodes.filter((n) => n.status === 'dead');
    if (hideTests) nodes = nodes.filter((n) => n.status !== 'test');
    if (hideEntryPoints) nodes = nodes.filter((n) => n.status !== 'entry');
    /* 对齐原生引擎 deadCodeView：按 status 重着色，覆盖引擎恒星色 */
    if (colorByStatus) {
      nodes = nodes.map((n) => ({
        ...n,
        color: colorForStatus(n.status || ''),
      }));
    }
    const ids = new Set(nodes.map((n) => n.id));
    let edges = render.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    if (edgeTypeFilter) {
      edges = edges.filter((e) => edgeTypeFilter.has(e.type || e.relation || ''));
    }
    return applyL1Layout({ ...render, nodes, edges }, layoutMode);
  }, [
    render,
    nodeTypeFilter,
    edgeTypeFilter,
    showOnlyDead,
    colorByStatus,
    hideTests,
    hideEntryPoints,
    layoutMode,
  ]);

  // 项目 id / 当前布局节点边数写给页面感知 provider(§9.20);数据未到记 null,不编数字
  useEffect(() => {
    if (!id) {
      rememberCodeGraphDetail(null);
      return;
    }
    rememberCodeGraphDetail({
      projectId: id,
      nodes: filtered ? filtered.nodes.length : null,
      edges: filtered ? filtered.edges.length : null,
    });
  }, [id, filtered]);

  useEffect(() => {
    if (selectedPath) return;
    if (!searchQuery || !filtered) {
      if (!selectedPath) setHighlightedIds(null);
      return;
    }
    const q = searchQuery.toLowerCase();
    const matches = filtered.nodes.filter(
      (n) =>
        n.name.toLowerCase().includes(q) ||
        (n.qualified_name || '').toLowerCase().includes(q) ||
        (n.file_path || '').toLowerCase().includes(q),
    );
    const ids = new Set(matches.map((n) => n.id));
    setHighlightedIds(ids.size ? ids : null);
    if (ids.size) setCameraTarget(computeCameraTarget(filtered.nodes, ids));
  }, [searchQuery, filtered, selectedPath]);

  useEffect(() => {
    if (!filtered?.nodes.length) return;
    if (selectedNode || selectedPath) return;
    const ids = new Set(filtered.nodes.map((n) => n.id));
    setCameraTarget(computeCameraTarget(filtered.nodes, ids));
    // 仅在节点数量/布局变化时重置相机，避免 filtered 引用抖动
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 有意依赖 nodes.length
  }, [filtered?.nodes.length, id, layoutMode, selectedNode, selectedPath]);

  const onSelectPath = (path: string, nodeIds: Set<number>) => {
    if (!path || nodeIds.size === 0) {
      setSelectedPath(null);
      setHighlightedIds(null);
      selectNode(null);
      return;
    }
    setSelectedPath(path);
    setHighlightedIds(nodeIds);
    if (filtered) {
      setCameraTarget(computeCameraTarget(filtered.nodes, nodeIds));
      const candidates = filtered.nodes.filter((n) => nodeIds.has(n.id));
      const prefer =
        candidates.find((n) => (n.kind || n.label) === 'File') ||
        candidates.find((n) => (n.file_path || '') === path) ||
        candidates[0];
      if (prefer) selectNode(prefer);
    }
  };

  const onNodeClick = (node: CodeGraphNode) => {
    selectNode(node);
    if (!filtered) return;
    const neigh = new Set<number>([node.id]);
    for (const e of filtered.edges) {
      if (e.source === node.id) neigh.add(e.target);
      if (e.target === node.id) neigh.add(e.source);
    }
    setHighlightedIds(neigh);
    setCameraTarget(computeCameraTarget(filtered.nodes, new Set([node.id])));
  };

  const projectName = projectQ.data?.data?.name || id;
  const statusSlot = (
    <IndexStatusBar
      status={status}
      loading={
        statusQ.isLoading || trigger.isPending || refresh.isPending || delIndex.isPending
      }
      onIndex={(mode) => trigger.mutate(mode)}
      onRefresh={(mode) => refresh.mutate(mode)}
      onDelete={() => {
        const name = projectQ.data?.data?.name || id || '该项目';
        if (
          window.confirm(
            `删除「${name}」的索引？\n将清理本地克隆缓存与图谱数据库，不可恢复。`,
          )
        ) {
          delIndex.mutate();
        }
      }}
      nodeBudget={nodeBudget}
      onBudgetChange={setNodeBudget}
      totalNodes={filtered?.total_nodes ?? status?.node_count ?? undefined}
      shownNodes={filtered?.nodes.length}
      shownEdges={filtered?.edges.length}
    />
  );

  return (
    <div className="code-graph-page">
      <div className="code-graph-stage">
        <CodeGraphSidebar
          data={filtered}
          selectedPath={selectedPath}
          onSelectPath={onSelectPath}
          layoutMode={layoutMode}
          onLayoutModeChange={setLayoutMode}
          statusSlot={statusSlot}
        />

        {statusQ.isError && (
          <div
            className="code-graph-empty glass-card glass-card--overview-inner"
            style={{
              border: '1px solid rgba(255,55,95,.28)',
              background: 'var(--error-bg, rgba(239,68,68,.08))',
            }}
          >
            <h2 style={{ color: 'var(--error)' }}>代码图谱服务不可用</h2>
            <p>{(statusQ.error as Error)?.message || '无法获取索引状态'}</p>
          </div>
        )}

        {!ready && !statusQ.isError && (
          <div className="code-graph-empty glass-card glass-card--overview-inner">
            <h2>尚未构建代码图谱</h2>
            <p>
              {status?.status === 'CLONE_FAILED' || status?.status === 'INDEX_FAILED'
                ? status.error || '克隆或索引失败，请重试'
                : status && ['QUEUED', 'CLONING', 'INDEXING'].includes(status.status)
                  ? `正在处理：${status.status}`
                  : '请先浅克隆 GitHub 仓库并构建代码图谱。'}
            </p>
            {(!status ||
              ['NONE', 'CLONE_FAILED', 'INDEX_FAILED', 'STALE'].includes(status.status)) && (
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => trigger.mutate('moderate')}
                disabled={trigger.isPending}
              >
                开始索引
              </button>
            )}
          </div>
        )}

        {ready && graphQ.isLoading && <LoadingSpinner />}
        {ready && graphQ.isError && (
          <div className="code-graph-empty glass-card glass-card--overview-inner">
            <h2>加载代码图谱失败</h2>
            <p>{(graphQ.error as Error)?.message || '无法获取布局数据'}</p>
          </div>
        )}
        {ready && filtered && (
          <>
            <div className="code-graph-display-dock">
              <DisplaySettingsMenu settings={display} onChange={updateDisplay} />
            </div>
            <GraphScene
              data={filtered}
              highlightedIds={highlightedIds}
              cameraTarget={cameraTarget}
              showLabels={showLabels}
              enableBloom
              display={effectiveDisplay}
              onNodeClick={onNodeClick}
              onBackgroundClick={() => {
                selectNode(null);
                setHighlightedIds(null);
                setSelectedPath(null);
              }}
            />
          </>
        )}

        {selectedNode && id && (
          <NodeDetailPanel
            node={selectedNode}
            allNodes={filtered?.nodes || []}
            allEdges={filtered?.edges || []}
            projectId={id}
            onClose={() => selectNode(null)}
            onNavigate={onNodeClick}
          />
        )}

        <div className="code-graph-footer glass-card glass-card--overview-inner">
          <span className="stat-row">
            <span className="stat-dot" />
            <span className="stat-mono">
              {filtered
                ? `${filtered.nodes.length} 节点 / ${filtered.edges.length} 连线`
                : projectName}
            </span>
          </span>
        </div>
      </div>

      <GraphGuidePanel selectedNodeId={id ?? null} />
    </div>
  );
}
