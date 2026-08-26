// @ts-nocheck — 迁移期:上游迁入的代码,字段重命名由 legacyApi 边界归一化,新 page / hook 仍按 strict 写(见各文件顶部注释)。
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

export function useGithubStars(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['githubStars'],
    queryFn: async () => {
      const api = getApi();
      // 默认走服务端缓存；强制刷新由 mutate/invalidate + listStars({refresh:true}) 触发
      const res = await api.listStars();
      return res.data;
    },
    enabled: options?.enabled !== false,
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
