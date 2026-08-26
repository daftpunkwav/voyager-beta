/** 服务状态 — 实时健康探测(由 gateway /health 聚合)。
 *
 * 入口走 /health 端点(各 service probe + overall 状态)。
 * 展示每服务的状态徽章 + 最近状态变化时间。
 */

import { useEffect, useState } from 'react';
import { GlassCard } from '@/widgets/GlassCard';
import { LoadingSpinner } from '@/widgets/LoadingSpinner';
import { EmptyState } from '@/widgets/EmptyState';

interface HealthRecord {
  service: string;
  status: 'up' | 'down' | 'degraded' | 'unknown';
  detail?: string;
  ts?: number;
}

interface HealthPayload {
  overall?: 'up' | 'down' | 'degraded' | 'unknown';
  services?: HealthRecord[];
}

export function HealthPage() {
  const [payload, setPayload] = useState<HealthPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const fetchHealth = async () => {
      try {
        const resp = await fetch('/api/activity/feed?kind=service.health.changed');
        // 真实端点是 /api/activity/feed 的事件流;聚合状态在 /health
        // 这里直接调 gateway /health(由 servicebadge 转发)
        const healthResp = await fetch('/health');
        if (!healthResp.ok) throw new Error(`HTTP ${healthResp.status}`);
        const body = (await healthResp.json()) as HealthPayload;
        if (!alive) return;
        setPayload(body);
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (alive) setLoading(false);
      }
    };
    void fetchHealth();
    const t = window.setInterval(fetchHealth, 15000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, []);

  return (
    <div className="health-page">
      <h1 className="h2">服务状态</h1>
      {loading ? (
        <LoadingSpinner label="加载健康状态中…" />
      ) : error ? (
        <EmptyState title="无法获取状态" message={error} />
      ) : !payload ? (
        <EmptyState title="无数据" />
      ) : (
        <>
          <GlassCard className={`health-overall health-overall--${payload.overall ?? 'unknown'}`}>
            <span className="label">整体</span>
            <span className="value">{payload.overall ?? 'unknown'}</span>
          </GlassCard>
          <h2 className="h3">服务</h2>
          <div className="health-grid">
            {(payload.services ?? []).map((s) => (
              <GlassCard key={s.service} className={`health-card health-card--${s.status}`}>
                <div className="health-card__head">
                  <span className="health-card__name mono">{s.service}</span>
                  <span className={`chip health-chip--${s.status}`}>{s.status}</span>
                </div>
                {s.detail ? <p className="muted small">{s.detail}</p> : null}
                {s.ts ? (
                  <p className="small mono">最近探测:{new Date(s.ts * 1000).toLocaleString()}</p>
                ) : null}
              </GlassCard>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export default HealthPage;
