import { useGraphStore } from '@/stores/graphStore';
import type { GraphLayoutMode, GraphViewMode } from '@/stores/graphStore';
import { L0_EDGE_TYPES } from '@/components/graph/l0EdgeTypes';
import { GraphIndexProgressBar } from '@/components/graph/GraphIndexProgressBar';
import type { MouseEvent, ReactNode } from 'react';

interface GraphControlsProps {
  showLayout?: boolean;
  viewModes?: { id: GraphViewMode; label: string }[];
  viewMode?: GraphViewMode;
  onViewModeChange?: (mode: GraphViewMode) => void;
  /** 批量索引入口（挂在左上信息栏，避免与 Atlas 重叠） */
  batchSlot?: ReactNode;
}

const LAYOUTS: { id: GraphLayoutMode; label: string }[] = [
  { id: 'force', label: '力导向' },
  { id: 'tree', label: '树状' },
  { id: 'radial', label: '径向' },
];

/** 图谱顶栏：单列列表式排布，可收起 */
export function GraphControls({
  showLayout = true,
  viewModes,
  viewMode,
  onViewModeChange,
  batchSlot,
}: GraphControlsProps) {
  const searchQuery = useGraphStore((s) => s.searchQuery);
  const setSearchQuery = useGraphStore((s) => s.setSearchQuery);
  const minSimilarity = useGraphStore((s) => s.minSimilarity);
  const setMinSimilarity = useGraphStore((s) => s.setMinSimilarity);
  const layoutMode = useGraphStore((s) => s.layoutMode);
  const setLayoutMode = useGraphStore((s) => s.setLayoutMode);
  const edgeTypeFilter = useGraphStore((s) => s.edgeTypeFilter);
  const setEdgeTypeFilter = useGraphStore((s) => s.setEdgeTypeFilter);
  const kindsFilter = useGraphStore((s) => s.kindsFilter);
  const toggleKindFilter = useGraphStore((s) => s.toggleKindFilter);
  const leftPanelCollapsed = useGraphStore((s) => s.leftPanelCollapsed);
  const setLeftPanelCollapsed = useGraphStore((s) => s.setLeftPanelCollapsed);

  const showUniverseExtras = showLayout && viewMode !== 'list';

  const KIND_CHIPS: { id: string; label: string }[] = [
    { id: 'repo', label: '仓库' },
    { id: 'doc', label: '文档' },
    { id: 'web', label: '网页' },
  ];
  const isKindActive = (id: string) => !kindsFilter || kindsFilter.has(id);

  const handlePanelClick = (e: MouseEvent<HTMLDivElement>) => {
    if (leftPanelCollapsed) return;
    // 仅当点击的是工具栏容器本身时才收起；子元素不触发
    if (e.target !== e.currentTarget) return;
    setLeftPanelCollapsed(true);
  };

  return (
    <div
      data-graph-toolbar
      className={`graph-toolbar graph-toolbar--column glass-card glass-card--overview-outer${
        leftPanelCollapsed ? ' is-collapsed' : ''
      }`}
      title={leftPanelCollapsed ? undefined : '点击空白处收起'}
      onClick={handlePanelClick}
    >
      {leftPanelCollapsed ? (
        <button
          type="button"
          className="graph-toolbar__toggle"
          title="展开信息栏"
          aria-label="展开信息栏"
          aria-expanded={false}
          onClick={() => setLeftPanelCollapsed(false)}
        >
          ⟩
        </button>
      ) : (
        <>
          <label className="graph-search">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="7" />
              <path d="M21 21l-4.3-4.3" />
            </svg>
            <input
              placeholder="搜索 owner/repo"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </label>

          {viewModes && viewMode && onViewModeChange && (
            <div className="graph-toolbar__row">
              <span className="graph-toolbar__label">视图</span>
              <div className="view-switch" role="group" aria-label="展示形态">
                {viewModes.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    className={viewMode === m.id ? 'active' : undefined}
                    onClick={() => onViewModeChange(m.id)}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
              {/* 边类型图例仅挂在「宇宙图」下；列表模式不展示 */}
              {showUniverseExtras && (
                <div className="graph-legend graph-legend--under-view" aria-label="边类型">
                  <button
                    type="button"
                    className={`legend-item${!edgeTypeFilter ? ' is-active' : ''}`}
                    onClick={() => setEdgeTypeFilter(null)}
                    title="全部边类型"
                  >
                    <span className="legend-dot" style={{ background: 'var(--text-400)' }} />
                    <span className="legend-item__text">全部</span>
                  </button>
                  {L0_EDGE_TYPES.map((l) => (
                    <button
                      key={l.id}
                      type="button"
                      className={`legend-item${edgeTypeFilter === l.id ? ' is-active' : ''}`}
                      onClick={() =>
                        setEdgeTypeFilter(edgeTypeFilter === l.id ? null : l.id)
                      }
                      title={l.label}
                    >
                      <span className="legend-dot" style={{ background: l.color }} />
                      <span className="legend-item__text">{l.label}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {showUniverseExtras && (
            <div className="graph-toolbar__row">
              <span className="graph-toolbar__label">类型</span>
              <div className="view-switch" role="group" aria-label="参与关联的资源种类">
                {KIND_CHIPS.map((k) => (
                  <button
                    key={k.id}
                    type="button"
                    className={isKindActive(k.id) ? 'active' : undefined}
                    title={kindsFilter?.has(k.id) === false ? `纳入${k.label}参与关联` : `从关联分析中排除${k.label}`}
                    onClick={() => toggleKindFilter(k.id)}
                  >
                    {k.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {showUniverseExtras && (
            <div className="graph-toolbar__row">
              <span className="graph-toolbar__label">布局</span>
              <div className="layout-switch" role="group" aria-label="三维布局算法">
                {LAYOUTS.map((l) => (
                  <button
                    key={l.id}
                    type="button"
                    className={layoutMode === l.id ? 'active' : undefined}
                    onClick={() => setLayoutMode(l.id)}
                  >
                    {l.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {showUniverseExtras && (
            <div className="graph-toolbar__row">
              <span className="graph-toolbar__label">阈值</span>
              <label className="graph-threshold" title="仅显示相似度 ≥ 此值的边">
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={minSimilarity}
                  onChange={(e) => setMinSimilarity(Number(e.target.value))}
                  aria-label="最小相似度阈值"
                />
                <span className="graph-threshold__value">{minSimilarity.toFixed(2)}</span>
              </label>
            </div>
          )}

          <div className="graph-toolbar__row graph-toolbar__row--index">
            <GraphIndexProgressBar />
          </div>

          {batchSlot && (
            <div className="graph-toolbar__row graph-toolbar__row--batch">{batchSlot}</div>
          )}
        </>
      )}
    </div>
  );
}

export { getSimilarNodes } from './graphHelpers';
