/** 用量卡:近 7 天 tokens 与调用次数(大数字与用量页同源)。 */

import { callCapability } from '@/bridge/client';
import { useCard } from '../OverviewPage';
import { CardShell } from './CardShell';

export function UsageCard() {
  const card = useCard(() => callCapability<{ input_tokens: number; output_tokens: number; calls: number }>(
    'llm', 'get_usage_stats', { days: 7 },
  ));

  return (
    <CardShell
      title="用量 · 近 7 天"
      to="/usage"
      error={card.error ? { code: (card.error as { code?: string }).code ?? 'LLM.UNAVAILABLE',
                            message: (card.error as Error).message } : undefined}
      onRetry={card.retry}
      loading={card.data === undefined && !card.error}
    >
      <div className="overview-nums">
        <div>
          <div className="overview-nums__value">{card.data?.input_tokens ?? 0}</div>
          <div className="small muted">输入 tokens</div>
        </div>
        <div>
          <div className="overview-nums__value">{card.data?.output_tokens ?? 0}</div>
          <div className="small muted">输出 tokens</div>
        </div>
        <div>
          <div className="overview-nums__value">{card.data?.calls ?? 0}</div>
          <div className="small muted">调用次数</div>
        </div>
      </div>
    </CardShell>
  );
}
