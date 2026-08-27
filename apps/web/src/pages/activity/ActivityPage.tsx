/** 活动 — 事件流回放 + 摘要。
 *
 * 入口走 /api/activity/feed(读事件流),按类型汇总最近 N 条。
 * 适配 docs/architecture.md §10.8 活动页要求:agent 做的一切在 UI 可见、可查、可撤销。
 */

import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { GlassCard } from '@/widgets/GlassCard';
import { LoadingSpinner } from '@/widgets/LoadingSpinner';
import { EmptyState } from '@/widgets/EmptyState';
import { summarize, type FeedEvent } from '@/bridge/feed';
import { extractErrorMessage } from '@/utils/errors';

interface FetchResp {
  events?: FeedEvent[];
  items?: FeedEvent[];
}

const KIND_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: '全部' },
  { value: 'user.message', label: '用户消息' },
  { value: 'agent.message', label: 'Agent 消息' },
  { value: 'task.progress', label: '任务进度' },
  { value: 'note.created', label: '笔记' },
  { value: 'source.added', label: '资源' },
  { value: 'settings.changed', label: '设置' },
];

export function ActivityPage() {
  const [params, setParams] = useSearchParams();
  const kind = params.get('kind') ?? '';
  const [events, setEvents] = useState<FeedEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    (async () => {
      try {
        const url = new URL('/api/activity/feed', window.location.origin);
        if (kind) url.searchParams.set('kind', kind);
        const resp = await fetch(url.toString());
        if (!resp.ok) {
          // 优先透出后端 JSON 信封里的 message;无信封(如代理在后端未启动时的 500)给网络提示
          const body = (await resp.json().catch(() => null)) as { error?: { message?: string } } | null;
          throw new Error(body?.error?.message ?? '无法连接后端服务，请确认后端已启动');
        }
        const body = (await resp.json()) as FetchResp;
        if (!alive) return;
        setEvents(body.events ?? body.items ?? []);
      } catch (err) {
        if (alive) setError(extractErrorMessage(err));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [kind]);

  return (
    <div className="activity-page">
      <header className="activity-page__head">
        <h1 className="h2">活动</h1>
        <select
          className="filter-native-select"
          value={kind}
          onChange={(e) => {
            const v = e.target.value;
            if (v) setParams({ kind: v });
            else setParams({});
          }}
        >
          {KIND_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </header>

      {loading ? (
        <LoadingSpinner label="加载活动流中…" />
      ) : error ? (
        <EmptyState title="加载失败" message={error} />
      ) : events.length === 0 ? (
        <EmptyState title="暂无活动" message="(此时间段内无事件)" />
      ) : (
        <GlassCard className="activity-card">
          <ul className="activity-list">
            {events.map((ev) => {
              const s = summarize(ev);
              return (
                <li key={ev.seq ?? `${ev.ts}-${ev.id}`} className={`activity-row activity-row--${s.tone}`}>
                  <span className="small mono">{ev.ts ? new Date(ev.ts * 1000).toLocaleString() : ''}</span>
                  <span className="activity-row__text">{s.text}</span>
                </li>
              );
            })}
          </ul>
        </GlassCard>
      )}
    </div>
  );
}

export default ActivityPage;
