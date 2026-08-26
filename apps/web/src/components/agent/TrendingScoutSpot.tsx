import { AgentAvatar, type LookTarget } from '@/components/agent/AgentAvatar';
import { OVERVIEW_CHIP_GLASS } from '@/constants/overviewGlass';
import type { TrendingRepo } from '@/api/types';
import type { TrendingScoutPhase } from '@/hooks/useTrendingScoutSpot';
import type { CSSProperties } from 'react';

interface TrendingScoutSpotProps {
  phase: TrendingScoutPhase;
  repo: TrendingRepo | null;
  content: string;
  isStreaming: boolean;
  lookTarget: LookTarget | null;
  bubbleWidthPx: number | null;
}

export function TrendingScoutSpot({
  phase,
  repo,
  content,
  isStreaming,
  lookTarget,
  bubbleWidthPx,
}: TrendingScoutSpotProps) {
  if (phase === 'hidden' || !repo) return null;

  const name = `${repo.owner}/${repo.repo}`;
  const bubbleStyle = bubbleWidthPx
    ? ({ '--scout-bubble-width': `${bubbleWidthPx}px` } as CSSProperties)
    : undefined;

  return (
    <div
      className={`trending-scout-spot trending-scout-spot--${phase}`}
      style={bubbleStyle}
      aria-live="polite"
      aria-label={`Scout 正在介绍 ${name}`}
    >
      <div className={`trending-scout-bubble overview-control-surface ${OVERVIEW_CHIP_GLASS}`}>
        <span className="trending-scout-bubble-label">Scout</span>
        <p className="trending-scout-bubble-text">
          {content}
          {isStreaming ? <span className="trending-scout-stream-cursor" aria-hidden /> : null}
        </p>
      </div>
      <AgentAvatar
        agentId="scout"
        lookTarget={lookTarget}
        isFocused={false}
        blink
        size={58}
      />
    </div>
  );
}
