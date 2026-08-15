/** 手建节点/边表单:label 下拉 + 关系类型;边端点用 qualified_name,
 * 端点不存在时服务端自动补占位节点(提示用户)。
 */

import { useState } from 'react';
import { useGraphStore } from './graphStore';

const NODE_LABELS = ['Concept', 'Topic', 'Term', 'Project', 'Module', 'Class',
  'Function', 'File', 'Note', 'Person', 'Organization', 'Event'];
const REL_TYPES = ['RELATES_TO', 'DEPENDS_ON', 'CONTAINS', 'EXPLAINS',
  'MENTIONS', 'PART_OF', 'CALLS', 'IMPORTS'];

export function NodeEditor({ onDone }: { onDone: () => void }) {
  const project = useGraphStore((s) => s.project);
  const createNode = useGraphStore((s) => s.createNode);
  const createEdge = useGraphStore((s) => s.createEdge);

  const [mode, setMode] = useState<'node' | 'edge'>('node');
  const [label, setLabel] = useState('Concept');
  const [name, setName] = useState('');
  const [relType, setRelType] = useState('RELATES_TO');
  const [src, setSrc] = useState('');
  const [dst, setDst] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const submit = async () => {
    setBusy(true);
    setMessage('');
    try {
      if (mode === 'node') {
        await createNode({ label, name: name.trim() });
        setMessage(`已创建节点「${name.trim()}」`);
        setName('');
      } else {
        await createEdge({ src: src.trim(), dst: dst.trim(), type: relType });
        setMessage('已创建关系;两端不存在的节点已自动补占位节点');
        setSrc('');
        setDst('');
      }
    } catch (err) {
      setMessage((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const valid = project
    && (mode === 'node'
      ? name.trim().length > 0
      : src.trim().length > 0 && dst.trim().length > 0);

  return (
    <div className="node-editor">
      <div className="node-editor__tabs">
        <button
          type="button"
          className={`btn btn-sm ${mode === 'node' ? 'btn-primary' : ''}`}
          onClick={() => setMode('node')}
        >
          建节点
        </button>
        <button
          type="button"
          className={`btn btn-sm ${mode === 'edge' ? 'btn-primary' : ''}`}
          onClick={() => setMode('edge')}
        >
          连边
        </button>
        <span className="sources-toolbar__spacer" />
        <button type="button" className="btn btn-sm" onClick={onDone}>
          关闭
        </button>
      </div>

      {mode === 'node' ? (
        <>
          <label className="small muted">
            标签
            <select
              className="setting-input"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            >
              {NODE_LABELS.map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </label>
          <input
            className="setting-input"
            value={name}
            placeholder="节点名称(如:ReAct 模式)"
            onChange={(e) => setName(e.target.value)}
          />
        </>
      ) : (
        <>
          <label className="small muted">
            关系类型
            <select
              className="setting-input"
              value={relType}
              onChange={(e) => setRelType(e.target.value)}
            >
              {REL_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </label>
          <input
            className="setting-input mono"
            value={src}
            placeholder="起点 qualified_name(如:toy.main.run)"
            onChange={(e) => setSrc(e.target.value)}
          />
          <input
            className="setting-input mono"
            value={dst}
            placeholder="终点 qualified_name(如:ReAct 模式)"
            onChange={(e) => setDst(e.target.value)}
          />
        </>
      )}
      {message ? <div className="small node-editor__msg">{message}</div> : null}
      <button
        type="button"
        className="btn btn-primary"
        disabled={busy || !valid}
        onClick={() => void submit()}
      >
        {busy ? '提交中…' : mode === 'node' ? '创建节点' : '创建关系'}
      </button>
    </div>
  );
}
