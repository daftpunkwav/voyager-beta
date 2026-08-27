/** 活动页 provider:对外暴露索引级摘要，不暴露 store 实现。 */

import type { PageProbe } from '@/bridge/pageContext';
import { useActivityStore } from './activityStore';

export const activityProvider: PageProbe = {
  page: 'activity',
  report() {
    const { events, group } = useActivityStore.getState();
    return { summary: `活动流 ${events.length} 条,筛选 ${group}`, counts: { events: events.length } };
  },
};
