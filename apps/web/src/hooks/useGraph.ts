import { useQuery } from '@tanstack/react-query';
import { getApi } from '@/api/client';
import { useGraphStore } from '@/stores/graphStore';

export function useGraph() {
  const minSimilarity = useGraphStore((s) => s.minSimilarity);
  const maxEdges = useGraphStore((s) => s.maxEdges);

  return useQuery({
    queryKey: ['graph', minSimilarity, maxEdges],
    queryFn: async () => {
      const api = getApi();
      const res = await api.getGraph({
        min_similarity: minSimilarity,
        /* 兼容尚未热更的后端（旧 le=1000）；社区仍由后端全量边计算 */
        max_edges: Math.min(maxEdges, 1000),
      });
      return res.data;
    },
  });
}
