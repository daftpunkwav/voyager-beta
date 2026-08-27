/** 用量页 provider:对外暴露索引级摘要，不暴露 store 实现。 */

import type { PageProbe } from '@/bridge/pageContext';
import { useUsageStore } from './usageStore';

export const usageProvider: PageProbe = {
  page: 'usage',
  report() {
    const { stats } = useUsageStore.getState();
    if (!stats) return null;
    return {
      summary: `用量近 ${stats.days} 天:${stats.calls} 次调用`,
      counts: { calls: stats.calls },
    };
  },
};
