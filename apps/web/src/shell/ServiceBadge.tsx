/** 服务徽章条:订阅 service.health.changed + 初始拉取 /health;down 的服务红点。 */

import { useEffect, useState } from 'react';
import { subscribe } from '@/bridge/stream';
import { EventType } from '@/bridge/events';

interface ServiceState {
  [domain: string]: { status: string };
}

export function ServiceBadges() {
  const [services, setServices] = useState<ServiceState>({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let alive = true;
    fetch('/health')
      .then((r) => r.json())
      .then((body) => {
        if (alive) {
          setServices(body.services ?? {});
          setLoaded(true);
        }
      })
      .catch(() => setLoaded(false));

    const off = subscribe([EventType.SERVICE_HEALTH_CHANGED], (event) => {
      const { service, to } = event.payload as { service: string; to: string };
      setServices((prev) => ({ ...prev, [service]: { status: to } }));
    });
    return () => {
      alive = false;
      off();
    };
  }, []);

  if (!loaded) {
    return (
      <div className="svc-badges" role="status" aria-label="服务健康加载中">
        <span className="svc-badge svc-badge--loading" title="正在检查服务状态">
          <span className="svc-badge__dot" aria-hidden />
          <span className="svc-badge__label">服务</span>
        </span>
      </div>
    );
  }

  return (
    <div className="svc-badges" role="status" aria-label="服务健康">
      {Object.entries(services).map(([domain, s]) => (
        <span
          key={domain}
          className={`svc-badge ${s.status === 'up' ? 'svc-badge--up' : 'svc-badge--down'}`}
          title={`${domain}: ${s.status}`}
        >
          <span className="svc-badge__dot" aria-hidden />
          {domain}
        </span>
      ))}
    </div>
  );
}
