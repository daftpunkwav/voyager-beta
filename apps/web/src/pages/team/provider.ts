/** 团队页 provider:对外暴露索引级摘要，不暴露 store 实现。 */

import type { PageProbe } from '@/bridge/pageContext';
import { useTeamStore } from './teamStore';

export const teamProvider: PageProbe = {
  page: 'team',
  report() {
    const { running } = useTeamStore.getState();
    return {
      summary: `团队页:${running.length} 个实例运行中`,
      counts: { running: running.length },
    };
  },
};
