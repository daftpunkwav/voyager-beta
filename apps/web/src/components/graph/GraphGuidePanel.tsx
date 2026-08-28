import { useEffect, useState } from 'react';
import { EmbedAgentChat } from '@/widgets/EmbedAgentChat';
import { AgentAvatar, type LookTarget } from '@/components/agent/AgentAvatar';

interface GraphGuidePanelProps {
  selectedNodeId: string | null;
}

/**
 * Atlas 浮钮：对标总览页 Scout —— 右下角小人，点击开闭对话窗；眼球跟随指针。
 */
export function GraphGuidePanel({ selectedNodeId }: GraphGuidePanelProps) {
  const [open, setOpen] = useState(false);
  const [lookTarget, setLookTarget] = useState<LookTarget | null>(null);

  useEffect(() => {
    if (open) {
      setLookTarget(null);
      return;
    }

    const onPointerMove = (event: PointerEvent) => {
      setLookTarget({ x: event.clientX, y: event.clientY });
    };

    window.addEventListener('pointermove', onPointerMove, { passive: true });
    return () => window.removeEventListener('pointermove', onPointerMove);
  }, [open]);

  return (
    <div className={`atlas-scout${open ? ' is-open' : ''}`}>
      {open && (
        <div className="atlas-scout__panel glass-card glass-card--panel" role="dialog" aria-label="Atlas 对话">
          <header className="atlas-scout__head">
            <div>
              <strong>Atlas · 图谱向导</strong>
              <p>专用于解读项目关系网络</p>
            </div>
            <button
              type="button"
              className="atlas-scout__close"
              onClick={() => setOpen(false)}
              aria-label="关闭 Atlas"
            >
              ×
            </button>
          </header>
          <div className="atlas-scout__body">
            <EmbedAgentChat
              mode="graph"
              title="Atlas"
              subtitle=""
              agentInitial="A"
              agentClassName="agent-graph_guide"
              graphNodeId={selectedNodeId}
              placeholder="问我图谱结构、相似度含义…"
            />
          </div>
        </div>
      )}
      <button
        type="button"
        className="atlas-scout__fab"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={open ? '关闭 Atlas' : '打开 Atlas'}
        title={open ? '关闭 Atlas' : '打开 Atlas'}
      >
        <AgentAvatar
          agentId="navigator"
          lookTarget={lookTarget}
          isFocused={open}
          blink
          size={56}
        />
        <span className="atlas-scout__fab-label">Atlas</span>
      </button>
    </div>
  );
}
