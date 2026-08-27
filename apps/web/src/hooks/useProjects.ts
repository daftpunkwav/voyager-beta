import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useShallow } from 'zustand/react/shallow';
import { getApi } from '@/api/client';
import type { CreateProjectInput, Project, ProjectProgress } from '@/api/types';
import { useProjectStore } from '@/stores/projectStore';
import { invalidateOverviewQueries } from '@/utils/invalidateOverview';

/** 从 store 派生查询参数；必须用 useShallow，避免每次返回新对象触发无限重渲染 */
function useProjectListParams() {
  return useProjectStore(
    useShallow((s) => ({
      search: s.search || undefined,
      category_id: s.categoryId ?? undefined,
      language: s.language ?? undefined,
      progress: s.progress ?? undefined,
      tag_id: s.tagId ?? undefined,
      sort_by: s.sortBy,
      sort_order: s.sortOrder,
      page: s.page,
      page_size: s.pageSize,
    }))
  );
}

export function useProjects() {
  const params = useProjectListParams();
  return useQuery({
    queryKey: ['projects', params],
    queryFn: async () => {
      const api = getApi();
      const res = await api.listProjects(params);
      return res.data;
    },
  });
}

export function useProject(id: string | undefined) {
  return useQuery({
    queryKey: ['project', id],
    queryFn: async () => {
      if (!id) throw new Error('missing id');
      const api = getApi();
      const res = await api.getProject(id);
      return res.data;
    },
    enabled: Boolean(id),
  });
}

/** 按需拉取 GitHub README（详情 README tab） */
export function useProjectReadme(id: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ['projectReadme', id],
    queryFn: async () => {
      if (!id) throw new Error('missing id');
      const res = await getApi().getProjectReadme(id);
      return res.data;
    },
    enabled: Boolean(id) && enabled,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}

export function useProjectStats() {
  return useQuery({
    queryKey: ['projectStats'],
    queryFn: async () => {
      const api = getApi();
      const res = await api.getProjectStats();
      return res.data;
    },
  });
}

export function useCategories() {
  return useQuery({
    queryKey: ['categories'],
    queryFn: async () => {
      const api = getApi();
      const res = await api.listCategories();
      return res.data;
    },
  });
}

export function useTags() {
  return useQuery({
    queryKey: ['tags'],
    queryFn: async () => {
      const api = getApi();
      const res = await api.listTags();
      return res.data;
    },
  });
}

export function useTrending(period: 'daily' | 'weekly' | 'monthly', language?: string) {
  return useQuery({
    queryKey: ['trending', period, language],
    queryFn: async () => {
      const api = getApi();
      const res = await api.listTrending({ period, language });
      return res.data;
    },
  });
}

export function useActivities() {
  return useQuery({
    queryKey: ['activities'],
    queryFn: async () => {
      const api = getApi();
      const res = await api.listActivities();
      return res.data;
    },
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: CreateProjectInput) => {
      const api = getApi();
      const res = await api.createProject(data);
      return res.data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['projects'] });
      void invalidateOverviewQueries(qc);
    },
  });
}

export function useImportProjects() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (repos: Array<{ owner: string; repo: string; url: string }>) => {
      const api = getApi();
      const res = await api.importProjects(repos);
      return res.data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['projects'] });
      void invalidateOverviewQueries(qc);
    },
  });
}

export function useUpdateProgress() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, progress }: { id: string; progress: ProjectProgress }) => {
      const api = getApi();
      await api.updateProgress(id, progress);
    },
    onSuccess: (_d, vars) => {
      void qc.invalidateQueries({ queryKey: ['projects'] });
      void qc.invalidateQueries({ queryKey: ['project', vars.id] });
      void invalidateOverviewQueries(qc);
    },
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const api = getApi();
      await api.deleteProject(id);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['projects'] });
      void invalidateOverviewQueries(qc);
    },
  });
}

export function useUpdateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      data,
    }: {
      id: string;
      data: Partial<Project>;
    }) => {
      const res = await getApi().updateProject(id, data);
      return res.data;
    },
    onSuccess: (_d, vars) => {
      void qc.invalidateQueries({ queryKey: ['projects'] });
      void qc.invalidateQueries({ queryKey: ['project', vars.id] });
      void invalidateOverviewQueries(qc);
    },
  });
}

export function useCreateCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (name: string) => {
      const res = await getApi().createCategory({ name });
      return res.data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['categories'] });
    },
  });
}

export function useDeleteCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await getApi().deleteCategory(id);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['categories'] });
      void qc.invalidateQueries({ queryKey: ['projects'] });
    },
  });
}

export function useCreateTag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (name: string) => {
      const res = await getApi().createTag({ name });
      return res.data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['tags'] });
    },
  });
}

export function useDeleteTag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await getApi().deleteTag(id);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['tags'] });
      void qc.invalidateQueries({ queryKey: ['projects'] });
    },
  });
}

export function useSetProjectTags() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      projectId,
      tagIds,
    }: {
      projectId: string;
      tagIds: string[];
    }) => {
      const res = await getApi().setProjectTags(projectId, tagIds);
      return res.data;
    },
    onSuccess: (_d, vars) => {
      void qc.invalidateQueries({ queryKey: ['tags'] });
      void qc.invalidateQueries({ queryKey: ['projects'] });
      void qc.invalidateQueries({ queryKey: ['project', vars.projectId] });
    },
  });
}

/** GitHub stars 真桥接:list_starred_repos 需要用户名(本机单用户无内建账号,
 *  由抽屉让用户填一次,localStorage 记住)。原始 GitHub 条目适配 StarRepo 形态。 */
export function useGithubStars(options?: { username?: string; enabled?: boolean }) {
  const username = options?.username ?? '';
  return useQuery({
    queryKey: ['githubStars', username],
    queryFn: async () => {
      const api = getApi();
      const res = await api.listStars(username);
      const raw = (res.data?.items ?? []) as Array<{
        name?: string; html_url?: string; description?: string;
        stargazers_count?: number; language?: string | null;
        owner?: { login?: string };
      }>;
      const items = raw.map((r) => {
        const owner = r.owner?.login ?? '';
        const repo = r.name ?? '';
        return {
          full_name: `${owner}/${repo}`,
          owner,
          repo,
          description: r.description ?? '',
          stars: r.stargazers_count ?? 0,
          language: r.language,
          html_url: r.html_url ?? `https://github.com/${owner}/${repo}`,
          url: r.html_url ?? `https://github.com/${owner}/${repo}`,
        };
      });
      return { items, total: items.length, cached: false, fetched_at: Date.now() / 1000 };
    },
    enabled: (options?.enabled ?? true) && Boolean(username),
    staleTime: 5 * 60 * 1000,
  });
}

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

export type { Project };

/** 项目列表中出现过的语言集合(去重排序),供筛选栏使用。 */
export function useProjectLanguages(projects: Project[]): string[] {
  return useMemo(() => {
    const set = new Set<string>();
    for (const p of projects) {
      if (p.language) set.add(p.language);
    }
    return Array.from(set).sort();
  }, [projects]);
}
