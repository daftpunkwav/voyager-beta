import { useQuery } from '@tanstack/react-query';
import { getApi } from '@/api/client';

/** 总览 · Agent 个性化推荐 */
export function useRecommendedProjects(limit = 5) {
  return useQuery({
    queryKey: ['overview', 'recommendations', limit],
    queryFn: async () => {
      const api = getApi();
      const res = await api.listRecommendedProjects({ limit });
      return res.data;
    },
  });
}

/** 总览 · 最近笔记（含项目名称） */
export function useOverviewRecentNotes(limit = 4) {
  return useQuery({
    queryKey: ['overview', 'recentNotes', limit],
    queryFn: async () => {
      const api = getApi();
      const res = await api.listOverviewRecentNotes({ limit });
      return res.data;
    },
  });
}
