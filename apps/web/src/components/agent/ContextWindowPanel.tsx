import { useQuery } from '@tanstack/react-query';
import { getApi } from '@/api/client';
import type { ContextWindowStats } from '@/api/types';

export function useContextWindow(sessionId: string | null) {
  return useQuery({
    queryKey: ['contextWindow', sessionId],
    queryFn: async () => (await getApi().getContextWindow(sessionId)).data,
    // 15s 基础间隔 + 0~2s jitter，避免多面板同时打后端
    refetchInterval: 15000 + Math.floor(Math.random() * 2000),
    refetchIntervalInBackground: false,
  });
}

interface ContextWindowPanelProps {
  sessionId?: string | null;
  compact?: boolean;
}

export function ContextWindowPanel({ sessionId = null, compact }: ContextWindowPanelProps) {
  const { data } = useContextWindow(sessionId ?? null);

  if (!data) return null;

  const usedPct = Math.min(100, Math.round((data.total_tokens / data.context_limit) * 100));

  return (
    <div className={`ctx-window-panel ${compact ? 'ctx-window-panel--compact' : ''}`}>
      <div className="context-title">
        <span>上下文窗口</span>
        <span className="ctx-window-model">{data.model}</span>
      </div>
      <div className="ctx-window-stats">
        <div className="ctx-window-stat">
          <span className="k">输入</span>
          <span className="v mono">{data.input_tokens.toLocaleString()}</span>
        </div>
        <div className="ctx-window-stat">
          <span className="k">输出</span>
          <span className="v mono">{data.output_tokens.toLocaleString()}</span>
        </div>
        <div className="ctx-window-stat">
          <span className="k">合计</span>
          <span className="v mono">{data.total_tokens.toLocaleString()}</span>
        </div>
        <div className="ctx-window-stat">
          <span className="k">上限</span>
          <span className="v mono">{(data.context_limit / 1000).toFixed(0)}k</span>
        </div>
      </div>
      <div className="ctx-window-bar" aria-hidden>
        <span style={{ width: `${usedPct}%` }} />
      </div>
      <div className="ctx-window-segments">
        {data.segments.map((seg) => (
          <div key={seg.label} className="ctx-window-seg">
            <span className="ctx-window-seg-label">{seg.label}</span>
            <span className="ctx-window-seg-tokens mono">{seg.tokens}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export type { ContextWindowStats };
