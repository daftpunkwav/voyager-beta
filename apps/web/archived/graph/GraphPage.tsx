/** 图谱页:顶栏(项目/搜索/标签过滤/新建/队列)+ 画布 + 详情侧栏;
 * SSE 订阅 task.*(索引进度与完成刷新)与 graph.engine.fallback(徽标)。
 */

import { useEffect, useState } from 'react';
import { subscribe } from '@/bridge/stream';
import { Degraded } from '@/shell/Degraded';
import { GraphCanvas } from './GraphCanvas';
import { NodeDetail } from './NodeDetail';
import { NodeEditor } from './NodeEditor';
import { IndexPanel, type JobProgress } from './IndexPanel';
import { useGraphStore } from './graphStore';

const STREAM_PATTERNS = [
  'task.progress',
  'task.completed',
  'task.failed',
  'graph.engine.fallback',
];

const LABEL_FILTERS = ['', 'Module', 'Function', 'Class', 'Concept', 'Term', 'File'];

export function GraphPage() {
  const {
    loading, error, init, project, projects, keyword, label, stats,
    setProject, setFilter, searchLocate, dispatch, engine, refreshEngine,
  } = useGraphStore();
  const [panel, setPanel] = useState<'none' | 'editor' | 'index'>('none');
  const [progress, setProgress] = useState<Record<string, JobProgress>>({});

  useEffect(() => {
    void init();
  }, [init]);

  useEffect(
    () =>
      subscribe(STREAM_PATTERNS, (ev) => {
        dispatch(ev);
        const jid = String(ev.payload.job_id ?? '');
        if (ev.type === 'task.progress' && jid) {
          setProgress((p) => ({
            ...p,
            [jid]: {
              progress: Number(ev.payload.progress ?? 0),
              stage: String(ev.payload.stage ?? ''),
            },
          }));
        } else if (jid) {
          setProgress(({ [jid]: _drop, ...rest }) => rest);
        }
      }),
    [dispatch],
  );

  // 引擎徽标:面板未开时顶栏也要显示(数据在 store)
  useEffect(() => {
    if (!engine) void refreshEngine().catch(() => {});
  }, [engine, refreshEngine]);

  if (error) {
    return (
      <Degraded
        code={error.code}
        message={`图谱服务不可用:${error.message}`}
        hint="其余页面不受影响"
        onRetry={() => void init()}
      />
    );
  }

  return (
    <section className="graph-page">
      <div className="sources-toolbar">
        <label className="small muted">
          项目
          <select
            className="setting-input"
            style={{ width: 'auto', marginLeft: 6 }}
            value={project}
            onChange={(e) => setProject(e.target.value)}
          >
            {projects.length === 0 ? <option value="">(无)</option> : null}
            {projects.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </label>
        <input
          className="setting-input graph-search"
          value={keyword}
          placeholder="搜索函数名/概念…"
          onChange={(e) => setFilter({ keyword: e.target.value })}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void searchLocate();
          }}
        />
        <button type="button" className="btn btn-sm" onClick={() => void searchLocate()}>
          定位
        </button>
        <label className="small muted">
          标签
          <select
            className="setting-input"
            style={{ width: 'auto', marginLeft: 6 }}
            value={label}
            onChange={(e) => setFilter({ label: e.target.value })}
          >
            {LABEL_FILTERS.map((l) => (
              <option key={l || 'all'} value={l}>{l || '全部'}</option>
            ))}
          </select>
        </label>
        {stats ? (
          <span className="small muted">
            {stats.total_nodes} 节点 / {stats.total_edges} 边
          </span>
        ) : null}
        <span className="sources-toolbar__spacer" />
        <button
          type="button"
          className={`btn btn-sm ${panel === 'editor' ? 'btn-primary' : ''}`}
          onClick={() => setPanel(panel === 'editor' ? 'none' : 'editor')}
        >
          新建节点/边
        </button>
        <button
          type="button"
          className={`btn btn-sm ${panel === 'index' ? 'btn-primary' : ''}`}
          onClick={() => setPanel(panel === 'index' ? 'none' : 'index')}
        >
          索引队列
        </button>
      </div>

      <div className="graph-layout">
        <div className="graph-main">
          {loading ? (
            <div className="loading-spinner">
              <div className="spinner" />
            </div>
          ) : null}
          <GraphCanvas />
        </div>
        {panel === 'editor' ? <NodeEditor onDone={() => setPanel('none')} /> : null}
        {panel === 'index' ? (
          <IndexPanel onClose={() => setPanel('none')} progress={progress} />
        ) : null}
        <NodeDetail />
      </div>
    </section>
  );
}
