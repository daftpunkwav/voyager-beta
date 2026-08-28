/** 服务状态 — 实时健康探测(由 gateway /health 聚合)。
 *
 * 入口走 /health 端点(各 service probe + overall 状态)。
 * 展示每服务的状态徽章 + 最近状态变化时间。
 */

import { useEffect, useState } from 'react';
import { GlassCard } from '@/components/common/GlassCard';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { extractErrorMessage, BACKEND_UNREACHABLE } from '@/utils/errors';

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
  const [retryTick, setRetryTick] = useState(0);

  useEffect(() => {
    let alive = true;
    const fetchHealth = async () => {
      try {
        const healthResp = await fetch('/health', { credentials: 'include' });
        if (!healthResp.ok) {
          const errBody = (await healthResp.json().catch(() => null)) as { error?: { message?: string } } | null;
          throw new Error(errBody?.error?.message ?? BACKEND_UNREACHABLE);
        }
        const body = (await healthResp.json()) as HealthPayload;
        if (!alive) return;
        setPayload(body);
        setError(null);
      } catch (err) {
        if (alive) setError(extractErrorMessage(err));
      } finally {
        if (alive) setLoading(false);
      }
    };
    setLoading(true);
    void fetchHealth();
    const t = window.setInterval(fetchHealth, 15000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, [retryTick]);

  return (
    <div className="health-page page-scaffold">
      {loading ? (
        <LoadingSpinner label="加载健康状态中…" />
      ) : error ? (
        <div className="page-scaffold__state">
          <EmptyState
            title="无法获取状态"
            description={error}
            icon={EmptyStateIcons.health}
            onRetry={() => setRetryTick((n) => n + 1)}
          />
        </div>
      ) : !payload ? (
        <div className="page-scaffold__state">
          <EmptyState title="无数据" icon={EmptyStateIcons.health} />
        </div>
      ) : (
        <>
          <div className="page-scaffold__body">
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
          </div>
        </>
      )}
    </div>
  );
}

export default HealthPage;
