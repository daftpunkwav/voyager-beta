/** 总览页:六张只读聚合卡,各自独立请求、独立降级(坑 1:绝不在顶层
 * Promise.all——一个服务挂全页白屏违背故障隔离)。本页不拥有任何数据。
 */

import { useEffect, useRef, useState } from 'react';
import type { ServiceError } from '@/bridge/client';
import { HealthCard } from './cards/HealthCard';
import { ActivityCard } from './cards/ActivityCard';
import { UsageCard } from './cards/UsageCard';
import { TasksCard } from './cards/TasksCard';
import { SourcesCard } from './cards/SourcesCard';
import { NotesCard } from './cards/NotesCard';

export interface CardState<T> {
  data?: T;
  error?: ServiceError;
}

/** 每卡统一数据钩子:自己抓错(独立降级的实现基础),retry 触发重拉。 */
export function useCard<T>(
  fn: () => Promise<T>,
  deps: unknown[] = [],
): CardState<T> & { retry: () => void } {
  const [state, setState] = useState<CardState<T>>({});
  const retryRef = useRef(0);
  useEffect(() => {
    let alive = true;
    setState({});
    fn()
      .then((data) => alive && setState({ data }))
      .catch((error: ServiceError) => alive && setState({ error }));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, retryRef.current]);
  const retry = () => {
    retryRef.current += 1;
  };
  return { ...state, retry };
}

export function OverviewPage() {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    // 轻刷新:页面重新聚焦时让各卡重拉(保持只读仪表盘的时效)
    const onVisible = () => {
      if (document.visibilityState === 'visible') setTick((t) => t + 1);
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, []);

  return (
    <section className="overview-page" data-tick={tick}>
      <div className="usage-cards overview-grid">
        <HealthCard />
        <TasksCard />
        <UsageCard />
        <SourcesCard />
        <NotesCard />
        <ActivityCard />
      </div>
    </section>
  );
}
