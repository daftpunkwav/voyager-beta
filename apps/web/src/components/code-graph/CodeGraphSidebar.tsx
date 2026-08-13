import { useMemo, useState, type MouseEvent, type ReactNode } from 'react';
import type { CodeGraphData, CodeGraphNode } from './types';
import { useCodeGraphStore } from '@/stores/codeGraphStore';
import type { L1LayoutMode } from './l1Layout';
import { colorForLabel, STATUS_LEGEND } from './colors';

interface Props {
  data: CodeGraphData | null;
  selectedPath: string | null;
  onSelectPath: (path: string, nodeIds: Set<number>) => void;
  layoutMode: L1LayoutMode;
  onLayoutModeChange: (m: L1LayoutMode) => void;
  /** 索引进度 / 就绪状态（并入左栏，对标 L0 GraphIndexProgressBar） */
  statusSlot?: ReactNode;
}

interface DirNode {
  name: string;
  fullPath: string;
  children: Map<string, DirNode>;
  nodeIds: Set<number>;
  directNodes: CodeGraphNode[];
}

const LAYOUTS: { id: L1LayoutMode; label: string }[] = [
  { id: 'engine', label: '引擎' },
  { id: 'force', label: '力导向' },
  { id: 'tree', label: '树状' },
  { id: 'radial', label: '径向' },
];

/** 交互控件：点这些不触发收起 */
const INTERACTIVE_SELECTOR = [
  'button',
  'a',
  'input',
  'select',
  'textarea',
  'label',
  '[role="button"]',
  '[role="group"]',
  '.code-graph-search',
  '.code-graph-layout-switch',
  '.code-graph-filter-list',
  '.code-graph-tree',
  '.code-graph-dirs',
  '.code-graph-statusbar',
  '.check',
].join(', ');

function isInteractiveTarget(target: EventTarget | null): boolean {
  return target instanceof Element && Boolean(target.closest(INTERACTIVE_SELECTOR));
}

/** 对齐原生引擎 Sidebar.buildFileTree */
function buildFileTree(nodes: CodeGraphNode[]): DirNode {
  const root: DirNode = {
    name: '/',
    fullPath: '',
    children: new Map(),
    nodeIds: new Set(),
    directNodes: [],
  };
  for (const node of nodes) {
    if (!node.file_path) continue;
    const parts = node.file_path.replace(/\\/g, '/').split('/');
    let cur = root;
    for (let i = 0; i < parts.length - 1; i += 1) {
      if (!parts[i]) continue;
      let child = cur.children.get(parts[i]!);
      if (!child) {
        const prefix = parts.slice(0, i + 1).join('/');
        child = {
          name: parts[i]!,
          fullPath: prefix,
          children: new Map(),
          nodeIds: new Set(),
          directNodes: [],
        };
        cur.children.set(parts[i]!, child);
      }
      cur = child;
    }
    cur.directNodes.push(node);
  }
  const collect = (d: DirNode): Set<number> => {
    const ids = new Set<number>();
    for (const n of d.directNodes) ids.add(n.id);
    for (const c of d.children.values()) {
      for (const id of collect(c)) ids.add(id);
    }
    d.nodeIds = ids;
    return ids;
  };
  collect(root);
  return root;
}

function flattenSingleChild(dir: DirNode): DirNode {
  const children = new Map<string, DirNode>();
  for (const [key, child] of dir.children) {
    let flat = flattenSingleChild(child);
    while (flat.children.size === 1 && flat.directNodes.length === 0) {
      const entry = [...flat.children.entries()][0];
      if (!entry) break;
      const [sk, sc] = entry;
      flat = {
        ...sc,
        name: `${flat.name}/${sk}`,
        children: flattenSingleChild(sc).children,
      };
    }
    children.set(key, flat);
  }
  return { ...dir, children };
}

function TreeItem({
  dir,
  depth,
  onSelect,
  selectedPath,
}: {
  dir: DirNode;
  depth: number;
  onSelect: (path: string, ids: Set<number>) => void;
  selectedPath: string | null;
}) {
  const [expanded, setExpanded] = useState(depth < 2);
  const isSelected = selectedPath === dir.fullPath;
  const sorted = useMemo(
    () => [...dir.children.values()].sort((a, b) => a.name.localeCompare(b.name)),
    [dir.children],
  );
  const fileGroups = useMemo(() => {
    const m = new Map<string, CodeGraphNode[]>();
    for (const n of dir.directNodes) {
      const fp = (n.file_path || '').replace(/\\/g, '/') || `${dir.fullPath}/${n.name}`;
      if (!m.has(fp)) m.set(fp, []);
      m.get(fp)!.push(n);
    }
    return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [dir.directNodes, dir.fullPath]);

  return (
    <div className="code-graph-tree__branch">
      <button
        type="button"
        className={`code-graph-tree__row${isSelected ? ' is-on' : ''}`}
        style={{ paddingLeft: `${depth * 14 + 8}px` }}
        onClick={() => {
          setExpanded((v) => !v);
          onSelect(dir.fullPath, dir.nodeIds);
        }}
      >
        <span className="code-graph-tree__caret">{expanded ? '▾' : '▸'}</span>
        <span className="code-graph-tree__name">{dir.name}</span>
        <span className="count">{dir.nodeIds.size}</span>
      </button>
      {expanded && (
        <>
          {sorted.map((c) => (
            <TreeItem
              key={c.fullPath}
              dir={c}
              depth={depth + 1}
              onSelect={onSelect}
              selectedPath={selectedPath}
            />
          ))}
          {fileGroups.map(([fp, nodes]) => {
            const ids = new Set(nodes.map((n) => n.id));
            const fileName = fp.split('/').pop() || fp;
            const isFileOn = selectedPath === fp;
            return (
              <button
                key={fp}
                type="button"
                className={`code-graph-tree__file${isFileOn ? ' is-on' : ''}`}
                style={{ paddingLeft: `${(depth + 1) * 14 + 8}px` }}
                onClick={() => onSelect(fp, ids)}
              >
                <span className="dot" style={{ background: nodes[0]?.color }} />
                <span className="code-graph-tree__name mono">{fileName}</span>
                <span className="count">{nodes.length}</span>
              </button>
            );
          })}
        </>
      )}
    </div>
  );
}

/** L1 左侧浮动过滤栏 · 对标 L0 GraphControls（空白点击收起） */
export function CodeGraphSidebar({
  data,
  selectedPath,
  onSelectPath,
  layoutMode,
  onLayoutModeChange,
  statusSlot,
}: Props) {
  const {
    showLabels,
    setShowLabels,
    showOnlyDead,
    setShowOnlyDead,
    colorByStatus,
    setColorByStatus,
    hideTests,
    setHideTests,
    hideEntryPoints,
    setHideEntryPoints,
    toggleNodeType,
    nodeTypeFilter,
    searchQuery,
    setSearchQuery,
    leftPanelCollapsed,
    setLeftPanelCollapsed,
  } = useCodeGraphStore();

  const [dirSearch, setDirSearch] = useState('');
  const [kindsOpen, setKindsOpen] = useState(true);
  const [deadOpen, setDeadOpen] = useState(false);

  const kindCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const n of data?.nodes || []) {
      const k = n.kind || n.label;
      m.set(k, (m.get(k) || 0) + 1);
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [data]);

  const deadCount = useMemo(
    () => (data?.nodes || []).filter((n) => n.status === 'dead').length,
    [data],
  );

  const tree = useMemo(
    () => flattenSingleChild(buildFileTree(data?.nodes || [])),
    [data],
  );
  const topLevel = useMemo(
    () => [...tree.children.values()].sort((a, b) => a.name.localeCompare(b.name)),
    [tree],
  );

  const filteredFiles = useMemo(() => {
    if (!dirSearch.trim()) return null;
    const q = dirSearch.toLowerCase();
    return (data?.nodes || [])
      .filter(
        (n) =>
          n.name.toLowerCase().includes(q) ||
          (n.file_path || '').toLowerCase().includes(q),
      )
      .slice(0, 50);
  }, [data, dirSearch]);

  const handlePanelClick = (e: MouseEvent<HTMLElement>) => {
    if (leftPanelCollapsed) return;
    if (isInteractiveTarget(e.target)) return;
    setLeftPanelCollapsed(true);
  };

  return (
    <aside
      className={`code-graph-sidebar glass-card glass-card--overview-outer${
        leftPanelCollapsed ? ' is-collapsed' : ''
      }`}
      title={leftPanelCollapsed ? undefined : '点击空白处收起'}
      onClick={handlePanelClick}
    >
      {leftPanelCollapsed ? (
        <button
          type="button"
          className="code-graph-sidebar__toggle"
          title="展开信息栏"
          aria-label="展开信息栏"
          aria-expanded={false}
          onClick={() => setLeftPanelCollapsed(false)}
        >
          ⟩
        </button>
      ) : (
        <>
          {statusSlot}

          <div className="code-graph-sidebar__row">
            <span className="code-graph-sidebar__label">布局</span>
            <div className="code-graph-layout-switch" role="group" aria-label="L1 布局">
              {LAYOUTS.map((l) => (
                <button
                  key={l.id}
                  type="button"
                  className={layoutMode === l.id ? 'is-active' : ''}
                  onClick={() => onLayoutModeChange(l.id)}
                >
                  {l.label}
                </button>
              ))}
            </div>
          </div>

          <label className="code-graph-search">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
              <circle cx="11" cy="11" r="7" />
              <path d="M21 21l-4.3-4.3" />
            </svg>
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索符号 / 路径"
            />
          </label>

          <div className="code-graph-sidebar__row">
            <button
              type="button"
              className="code-graph-sidebar__section-toggle"
              aria-expanded={kindsOpen}
              onClick={() => setKindsOpen((v) => !v)}
            >
              <span className="code-graph-sidebar__label">节点类型</span>
              <span className="code-graph-sidebar__caret" aria-hidden>
                {kindsOpen ? '▾' : '▸'}
              </span>
            </button>
            {kindsOpen && (
              <ul className="code-graph-filter-list">
                {kindCounts.map(([kind, count]) => {
                  const on = !nodeTypeFilter || nodeTypeFilter.has(kind);
                  return (
                    <li key={kind}>
                      <button
                        type="button"
                        className={on ? 'is-on' : ''}
                        onClick={() => toggleNodeType(kind)}
                      >
                        <span className="dot" style={{ background: colorForLabel(kind) }} />
                        {kind}
                        <span className="count">{count}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <div className="code-graph-sidebar__row">
            <button
              type="button"
              className="code-graph-sidebar__section-toggle"
              aria-expanded={deadOpen}
              onClick={() => setDeadOpen((v) => !v)}
            >
              <span className="code-graph-sidebar__label">死代码 · {deadCount}</span>
              <span className="code-graph-sidebar__caret" aria-hidden>
                {deadOpen ? '▾' : '▸'}
              </span>
            </button>
            {deadOpen && (
              <div className="code-graph-sidebar__checks">
                <label className="check">
                  <input
                    type="checkbox"
                    checked={colorByStatus}
                    onChange={(e) => setColorByStatus(e.target.checked)}
                  />
                  按状态着色
                </label>
                {colorByStatus && (
                  <div className="code-graph-status-legend" aria-label="状态图例">
                    {STATUS_LEGEND.map((s) => (
                      <span key={s.status} className="code-graph-status-legend__item">
                        <span
                          className="dot"
                          style={{ background: s.color }}
                          aria-hidden
                        />
                        {s.label}
                      </span>
                    ))}
                  </div>
                )}
                <label className="check">
                  <input
                    type="checkbox"
                    checked={showOnlyDead}
                    onChange={(e) => setShowOnlyDead(e.target.checked)}
                  />
                  仅显示死代码
                </label>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={hideEntryPoints}
                    onChange={(e) => setHideEntryPoints(e.target.checked)}
                  />
                  隐藏入口点
                </label>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={hideTests}
                    onChange={(e) => setHideTests(e.target.checked)}
                  />
                  隐藏测试
                </label>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={showLabels}
                    onChange={(e) => setShowLabels(e.target.checked)}
                  />
                  显示标签
                </label>
              </div>
            )}
          </div>

          <section className="code-graph-dirs">
            <span className="code-graph-sidebar__label">目录</span>
            <input
              className="code-graph-dir-search"
              value={dirSearch}
              onChange={(e) => setDirSearch(e.target.value)}
              placeholder="检索目录 / 文件…"
            />
            <div className="code-graph-tree">
              {filteredFiles ? (
                filteredFiles.length === 0 ? (
                  <p className="code-graph-tree__empty">无匹配</p>
                ) : (
                  filteredFiles.map((n) => (
                    <button
                      key={n.id}
                      type="button"
                      className="code-graph-tree__file"
                      onClick={() => onSelectPath(n.file_path || '', new Set([n.id]))}
                    >
                      <span className="dot" style={{ background: n.color }} />
                      <span className="code-graph-tree__name">{n.name}</span>
                    </button>
                  ))
                )
              ) : (
                topLevel.map((c) => (
                  <TreeItem
                    key={c.fullPath}
                    dir={c}
                    depth={0}
                    onSelect={onSelectPath}
                    selectedPath={selectedPath}
                  />
                ))
              )}
            </div>
            {selectedPath && (
              <button
                type="button"
                className="btn btn-ghost code-graph-tree__clear"
                onClick={() => onSelectPath('', new Set())}
              >
                清除目录选中
              </button>
            )}
          </section>
        </>
      )}
    </aside>
  );
}
