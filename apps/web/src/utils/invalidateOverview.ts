import type { QueryClient } from '@tanstack/react-query';

/** 总览页相关 React Query 缓存键（mutation 后统一失效） */
export const overviewQueryKeys = {
  activities: ['activities'] as const,
  recentNotes: (limit: number) => ['overview', 'recentNotes', limit] as const,
  recommendations: (limit: number) => ['overview', 'recommendations', limit] as const,
  userProfile: ['userProfile'] as const,
  projectStats: ['projectStats'] as const,
};

/** 用户操作后刷新总览依赖的数据（不含 trending，由后端/定时更新） */
export function invalidateOverviewQueries(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: overviewQueryKeys.activities }),
    qc.invalidateQueries({ queryKey: ['overview', 'recentNotes'] }),
    qc.invalidateQueries({ queryKey: ['overview', 'recommendations'] }),
    qc.invalidateQueries({ queryKey: overviewQueryKeys.userProfile }),
    qc.invalidateQueries({ queryKey: overviewQueryKeys.projectStats }),
  ]);
}
