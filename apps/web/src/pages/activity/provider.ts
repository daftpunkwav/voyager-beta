/** 活动流页面 provider(§5.1) — 当前未对接真实事件流,先返回空摘要。 */

import type { PageProbe } from '@/bridge/pageContext';

export const activityProvider: PageProbe = {
  page: 'activity',
  report() {
    // 数据未就绪时返回 null,PageProbe 跳过本次上报(避免空报)
    return null;
  },
};
