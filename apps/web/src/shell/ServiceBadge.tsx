/** 服务徽章条:订阅 service.health.changed + 初始拉取 /health;down 的服务红点。
 * /health 不可达(后端未启动)时显示"离线"徽章并周期重试,不永久卡在加载态。 */

import { useEffect, useState } from 'react';
import { subscribe } from '@/bridge/stream';
import { EventType } from '@/bridge/events';

interface ServiceState {
  [domain: string]: { status: string };
}

const RETRY_MS = 30_000;

export function ServiceBadges() {
  const [services, setServices] = useState<ServiceState>({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const check = () => {
      fetch('/health')
        .then((r) => {
          if (!r.ok) throw new Error(String(r.status));
          return r.json();
        })
        .then((body) => {
          if (!alive) return;
          setServices(body.services ?? {});
          setLoaded(true);
        })
        .catch(() => {
          // 不可达:标记离线态,30s 后重试(后端可能稍后被拉起)
          if (!alive) return;
          setServices({});
          setLoaded(true);
          timer = setTimeout(check, RETRY_MS);
        });
    };
    check();

    const off = subscribe([EventType.SERVICE_HEALTH_CHANGED], (event) => {
      const { service, to } = event.payload as { service: string; to: string };
      setServices((prev) => ({ ...prev, [service]: { status: to } }));
    });
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
      off();
    };
  }, []);

  if (!loaded) {
    return (
      <div className="svc-strip">
        <div className="svc-badges" role="status" aria-label="服务健康加载中">
          <span className="svc-badge svc-badge--loading" title="正在检查服务状态">
            <span className="svc-badge__dot" aria-hidden />
            <span className="svc-badge__label">服务</span>
          </span>
        </div>
      </div>
    );
  }

  if (Object.keys(services).length === 0) {
    // 各页面错误/空态已自行提示后端不可达,避免全局重复占用顶部空间。
    return null;
  }

  return (
    <div className="svc-strip">
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
    </div>
  );
}
