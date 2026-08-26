/** 活动卡:feed 最近 10 条(只取摘要字段渲染,复用 EventRow 摘要函数)。 */

import { useCard } from '../OverviewPage';
import { CardShell } from './CardShell';
import { type FeedEvent, summarize } from '@/bridge/feed';

export function ActivityCard() {
  const card = useCard<FeedEvent[]>(async () => {
    const resp = await fetch('/api/activity/feed?limit=10');
    if (!resp.ok) throw new Error(`feed ${resp.status}`);
    const body = (await resp.json()) as { events: FeedEvent[] };
    return [...(body.events ?? [])].reverse(); // 最新在上
  });

  return (
    <CardShell
      title="最近活动"
      to="/activity"
      error={card.error ? { code: 'GATEWAY.UNAVAILABLE', message: (card.error as Error).message } : undefined}
      onRetry={card.retry}
      loading={card.data === undefined && !card.error}
    >
      {card.data && card.data.length === 0 ? (
        <div className="small muted">还没有事件。</div>
      ) : null}
      <div className="overview-activity">
        {(card.data ?? []).map((ev) => {
          const s = summarize(ev);
          return (
            <div key={ev.seq} className={`overview-activity__row overview-activity__row--${s.tone}`}>
              {s.text}
            </div>
          );
        })}
      </div>
    </CardShell>
  );
}
