import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getApi } from '@/api/client';
import type { GraphIndexStatus } from '@/components/code-graph/types';
import { toRenderGraph } from '@/components/code-graph/renderGraph';

function requireProjectId(projectId: string | undefined): string {
  if (!projectId) throw new Error('缺少 projectId');
  return projectId;
}

export function useIndexStatus(projectId: string | undefined) {
  return useQuery({
    queryKey: ['graph-index-status', projectId],
    enabled: Boolean(projectId),
    refetchInterval: (q) => {
      const s = q.state.data?.data?.status;
      if (s && ['QUEUED', 'CLONING', 'INDEXING'].includes(s)) return 2000;
      return false;
    },
    queryFn: async () => {
      const api = getApi();
      return api.getCodeGraphStatus(requireProjectId(projectId));
    },
  });
}

export function useCodeGraph(
  projectId: string | undefined,
  opts: { maxNodes: number; enabled: boolean },
) {
  return useQuery({
    queryKey: ['code-graph', projectId, opts.maxNodes],
    enabled: Boolean(projectId) && opts.enabled,
    queryFn: async () => {
      const api = getApi();
      const res = await api.getCodeGraph(requireProjectId(projectId), {
        max_nodes: opts.maxNodes,
      });
      return { ...res, render: toRenderGraph(res.data as never) };
    },
  });
}

export function useTriggerIndex(
  projectId: string | undefined,
  opts?: { onError?: (err: Error) => void },
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (mode: 'fast' | 'moderate' | 'full' = 'moderate') => {
      const api = getApi();
      return api.triggerCodeGraphIndex(requireProjectId(projectId), { mode });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['graph-index-status', projectId] });
    },
    onError: opts?.onError,
  });
}

export function useRefreshIndex(
  projectId: string | undefined,
  opts?: { onError?: (err: Error) => void },
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (mode: 'fast' | 'moderate' | 'full' = 'moderate') => {
      const api = getApi();
      return api.refreshCodeGraphIndex(requireProjectId(projectId), { mode });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['graph-index-status', projectId] });
    },
    onError: opts?.onError,
  });
}

export function useDeleteIndex(
  projectId: string | undefined,
  opts?: { onError?: (err: Error) => void },
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const api = getApi();
      return api.deleteCodeGraphIndex(requireProjectId(projectId));
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['graph-index-status', projectId] });
      qc.invalidateQueries({ queryKey: ['code-graph', projectId] });
      qc.invalidateQueries({ queryKey: ['graph-index-statuses'] });
    },
    onError: opts?.onError,
  });
}

export type { GraphIndexStatus };
