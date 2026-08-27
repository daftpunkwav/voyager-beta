/** 资源库页 provider:对外暴露索引级摘要，不暴露 store 实现。 */

import type { PageProbe } from '@/bridge/pageContext';
import { useSourcesStore } from './sourcesStore';

export const sourcesProvider: PageProbe = {
  page: 'sources',
  report() {
    const { repos, loading } = useSourcesStore.getState();
    if (loading && repos.length === 0) return null;
    const ready = repos.filter((r) => r.status === 'ready').length;
    return {
      summary: `${repos.length} 个仓库(${ready} 就绪)`,
      counts: { repos: repos.length, ready },
    };
  },
};
