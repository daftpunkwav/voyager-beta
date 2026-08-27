import { useQuery } from '@tanstack/react-query';
import { getApi } from '@/api/client';

/** 会话上下文窗口占用。自 ContextWindowPanel 拆出:数据获取与展示分离。 */
export function useContextWindow(sessionId: string | null) {
  return useQuery({
    queryKey: ['contextWindow', sessionId],
    queryFn: async () => (await getApi().getContextWindow(sessionId)).data,
    // 15s 基础间隔 + 0~2s jitter，避免多面板同时打后端
    refetchInterval: 15000 + Math.floor(Math.random() * 2000),
    refetchIntervalInBackground: false,
  });
}
