import { useQuery } from '@tanstack/react-query';
import { getApi } from '@/api/client';

/** GitHub 账号绑定列表(settings 域)。自 useProjects 拆出:账号管理与项目库无耦合。 */
export function useGithubAccounts() {
  return useQuery({
    queryKey: ['githubAccounts'],
    queryFn: async () => {
      const api = getApi();
      const res = await api.listGithubAccounts();
      return res.data;
    },
  });
}
