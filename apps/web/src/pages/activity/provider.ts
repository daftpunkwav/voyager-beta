/** 活动流页感知:feed 拉到后报条数;加载中/失败不报(null)。 */

import type { PageProbe } from '@/bridge/pageContext';

/** null = feed 未就绪(加载中/失败);ActivityPage 拉到数据后写入。 */
let feedCount: number | null = null;

export function rememberActivityFeedCount(count: number | null): void {
  feedCount = count;
}

export function lastActivityFeedCount(): number | null {
  return feedCount;
}

export const activityProvider: PageProbe = {
  page: 'activity',
  report() {
    // 数据未就绪时返回 null,PageProbe 跳过本次上报(避免空报)
    const n = feedCount;
    if (n === null) return null;
    return { summary: `活动 · ${n} 条`, counts: { events: n } };
  },
};
