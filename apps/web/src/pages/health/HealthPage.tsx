/** 服务状态 — 实时健康探测(由 gateway /health 聚合)。
 *
 * 入口走 /health 端点(各 service probe + overall 状态)。
 * 展示每服务的状态徽章 + 最近状态变化时间。
 */

import { useEffect, useState } from 'react';
import { GlassCard } from '@/widgets/GlassCard';
import { LoadingSpinner } from '@/widgets/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/widgets/EmptyState';

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
        // §4.2.16 健康检查:直接 fetch gateway /health 端点;
        // 该端点不是 capability(只读健康摘要,无副作用),由 vite proxy 转发到 8000。
        // 若未来需鉴权,改为 callCapability('system', 'get_health', {})。
        const healthResp = await fetch('/health');
        if (!healthResp.ok) {
          // 无 JSON 信封的失败(代理在后端未启动时的 500)按网络不可达提示
          const errBody = (await healthResp.json().catch(() => null)) as { error?: { message?: string } } | null;
          throw new Error(errBody?.error?.message ?? '无法连接后端服务，请确认后端已启动');
        }
        const body = (await healthResp.json()) as HealthPayload;
        if (!alive) return;
        setPayload(body);
      } catch (err) {
        if (alive) {
          setError(err instanceof TypeError ? '无法连接后端服务，请确认后端已启动' : err instanceof Error ? err.message : String(err));
        }
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
    <div className="health-page page-scaffold">
      {loading ? (
        <LoadingSpinner label="加载健康状态中…" />
      ) : error ? (
        <div className="page-scaffold__state">
          <EmptyState
            title="无法获取状态"
            message={error}
            icon={EmptyStateIcons.health}
            action={
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => window.location.reload()}
              >
                刷新页面
              </button>
            }
          />
        </div>
      ) : !payload ? (
        <div className="page-scaffold__state">
          <EmptyState title="无数据" icon={EmptyStateIcons.health} />
        </div>
      ) : (
        <>
          <header className="page-scaffold__head">
            <div>
              <h1>服务状态</h1>
              <p className="page-scaffold__subtitle">实时健康探测与后端服务可用性</p>
            </div>
          </header>
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
