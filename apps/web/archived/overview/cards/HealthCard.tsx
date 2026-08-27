/** 健康卡:GET /health 各域状态点;订阅 service.health.changed 实时翻转。 */

import { useEffect, useState } from 'react';
import { subscribe } from '@/bridge/stream';
import { CardShell } from './CardShell';

interface ServiceState {
  [domain: string]: { status: string };
}

export function HealthCard() {
  const [services, setServices] = useState<ServiceState | null>(null);
  const [failed, setFailed] = useState(false);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    setServices(null);
    setFailed(false);
    fetch('/health')
      .then((r) => r.json())
      .then((body) => alive && setServices(body.services ?? {}))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [nonce]);

  useEffect(
    () =>
      subscribe(['service.health.changed'], (ev) => {
        const { service, to } = ev.payload as { service: string; to: string };
        setServices((prev) => (prev ? { ...prev, [service]: { status: to } } : prev));
      }),
    [],
  );

  return (
    <CardShell
      title="服务健康"
      to="/system/health"
      error={failed ? { code: 'GATEWAY.UNAVAILABLE', message: '无法获取服务状态' } : undefined}
      onRetry={() => setNonce((n) => n + 1)}
      loading={services === null}
    >
      <div className="svc-badges overview-health">
        {services
          ? Object.entries(services).map(([domain, s]) => (
              <span
                key={domain}
                className={`svc-badge ${s.status === 'up' ? 'svc-badge--up' : 'svc-badge--down'}`}
                title={`${domain}: ${s.status}`}
              >
                <span className="svc-badge__dot" aria-hidden />
                {domain}
              </span>
            ))
          : null}
      </div>
    </CardShell>
  );
}
