/** 节点详情:属性、出边入边(跳到对方节点)、来源(manual/ai/code)。
 * qualified_name 是"跳到代码"的依据(展示给用户,不展示内部 id,坑 2)。
 */

import { useMemo } from 'react';
import { useGraphStore } from './graphStore';

const SOURCE_LABELS: Record<string, string> = {
  manual: '手动',
  ai: 'AI 建图',
  code: '引擎解析',
};

export function NodeDetail() {
  const selected = useGraphStore((s) => s.selected);
  const nodes = useGraphStore((s) => s.nodes);
  const edges = useGraphStore((s) => s.edges);
  const select = useGraphStore((s) => s.select);
  const expand = useGraphStore((s) => s.expand);

  const node = selected ? nodes.get(selected) : null;
  const { outs, ins } = useMemo(() => {
    if (!node) return { outs: [], ins: [] };
    const all = [...edges.values()];
    return {
      outs: all.filter((e) => e.src === node.id),
      ins: all.filter((e) => e.dst === node.id),
    };
  }, [node, edges]);

  if (!node) {
    return (
      <aside className="node-detail node-detail--empty">
        <div className="muted small">点击节点查看详情;双击展开邻居。</div>
      </aside>
    );
  }

  const jump = (other: string) => {
    select(other);
    void expand(other);
  };

  return (
    <aside className="node-detail">
      <div className="node-detail__head">
        <span className="node-detail__dot" data-label={node.label} />
        <span className="node-detail__name">{node.name}</span>
        <span className="tag-chip">{node.label}</span>
        <span className="setting-badge setting-badge--none">
          {SOURCE_LABELS[node.source] ?? node.source}
        </span>
      </div>
      {node.qualified_name && node.qualified_name !== node.name ? (
        <div className="node-detail__qn mono small" title={node.qualified_name}>
          {node.qualified_name}
        </div>
      ) : null}
      {Object.keys(node.attrs ?? {}).length > 0 ? (
        <div className="node-detail__attrs">
          {Object.entries(node.attrs).slice(0, 8).map(([k, v]) => (
            <div key={k} className="small">
              <span className="muted">{k}:</span> {String(v).slice(0, 120)}
            </div>
          ))}
        </div>
      ) : null}
      <div className="node-detail__edges">
        <div className="label">出边({outs.length})</div>
        {outs.length === 0 ? <div className="small muted">无</div> : null}
        {outs.map((e) => (
          <button key={e.id} type="button" className="node-detail__edge" onClick={() => jump(e.dst)}>
            <span className="tag-chip">{e.type}</span>
            <span className="small">{nodes.get(e.dst)?.name ?? '未知节点'}</span>
          </button>
        ))}
        <div className="label">入边({ins.length})</div>
        {ins.length === 0 ? <div className="small muted">无</div> : null}
        {ins.map((e) => (
          <button key={e.id} type="button" className="node-detail__edge" onClick={() => jump(e.src)}>
            <span className="tag-chip">{e.type}</span>
            <span className="small">{nodes.get(e.src)?.name ?? '未知节点'}</span>
          </button>
        ))}
      </div>
    </aside>
  );
}
