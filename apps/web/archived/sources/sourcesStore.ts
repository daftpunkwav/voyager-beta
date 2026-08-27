/** 资源库状态:仓库列表/分类/排序 + SSE 进度与状态机(importing→ready/failed)。 */

import { create } from 'zustand';
import { callCapability, ServiceError } from '@/bridge/client';

export interface RepoSummary {
  id: string;
  owner: string;
  name: string;
  url: string;
  description: string;
  stars: number;
  language: string;
  category: string;
  tags: string[];
  progress: string; // none | learning | done
  note: string;
  local_path: string;
  status: 'importing' | 'ready' | 'failed';
  error: string;
  source: string;
  added_ts: number;
  updated_ts: number;
}

export interface CloneProgress {
  progress: number;
  stage: string;
}

export interface ImportOutcome {
  url: string;
  ok: boolean;
  message: string; // 成功:"已开始导入";CONFLICT:"已导入";失败:错误信息
}

interface SourcesState {
  repos: RepoSummary[];
  categories: string[];
  sort: 'name' | 'stars' | 'added' | 'updated';
  desc: boolean;
  category: string; // 筛选(空=全部)
  loading: boolean;
  error: { code: string; message: string } | null;
  /** SSE task.progress 进度条(source_id 维度) */
  progress: Record<string, CloneProgress>;
  init: () => Promise<void>;
  reload: () => Promise<void>;
  setView: (patch: Partial<Pick<SourcesState, 'sort' | 'desc' | 'category'>>) => void;
  importUrls: (urls: string[], category: string) => Promise<ImportOutcome[]>;
  setMeta: (
    repo_id: string,
    patch: { category?: string; tags?: string[]; progress?: string; note?: string },
  ) => Promise<void>;
  remove: (repo_id: string) => Promise<void>;
  /** SSE 事件(task.* / source.*);纯状态迁移,可单测。 */
  dispatch: (ev: { type: string; payload: Record<string, unknown> }) => void;
}

export const useSourcesStore = create<SourcesState>((set, get) => ({
  repos: [],
  categories: [],
  sort: 'added',
  desc: true,
  category: '',
  loading: false,
  error: null,
  progress: {},

  init: async () => {
    set({ loading: true, error: null });
    try {
      await get().reload();
      const categories = await callCapability<string[]>('sources', 'list_categories');
      set({ categories, loading: false });
    } catch (err) {
      const e = err as ServiceError;
      set({ loading: false, error: { code: e.code, message: e.message } });
    }
  },

  reload: async () => {
    const { sort, desc, category } = get();
    const repos = await callCapability<RepoSummary[]>('sources', 'list_repos', {
      sort,
      desc,
      category: category || '',
    });
    set({ repos });
  },

  setView: (patch) => {
    set(patch);
    void get().reload().catch(() => {
      // 视图切换失败保底:下次 init 重试
    });
  },

  importUrls: async (urls, category) => {
    const outcomes: ImportOutcome[] = [];
    for (const url of urls) {
      try {
        await callCapability<{ job_id: string }>('sources', 'import_repo', {
          url,
          category,
        });
        outcomes.push({ url, ok: true, message: '已开始导入' });
      } catch (err) {
        const e = err as ServiceError;
        // 已就绪仓库的重复导入是确认语义,不是错误(坑 1)
        const message = e.code.endsWith('CONFLICT')
          ? '已导入,无需重复'
          : e.hint
            ? `${e.message}(${e.hint})`
            : e.message;
        outcomes.push({ url, ok: e.code.endsWith('CONFLICT'), message });
      }
    }
    await get().reload().catch(() => {});
    set({ categories: await callCapability<string[]>('sources', 'list_categories').catch(() => get().categories) });
    return outcomes;
  },

  setMeta: async (repo_id, patch) => {
    const updated = await callCapability<RepoSummary>('sources', 'set_repo_meta', {
      repo_id,
      ...patch,
    });
    set({ repos: get().repos.map((r) => (r.id === repo_id ? { ...r, ...updated } : r)) });
  },

  remove: async (repo_id) => {
    await callCapability('sources', 'remove_repo', { repo_id });
    const { [repo_id]: _p, ...progress } = get().progress;
    set({
      repos: get().repos.filter((r) => r.id !== repo_id),
      progress,
    });
  },

  dispatch: (ev) => {
    const p = ev.payload;
    const sid = String(p.source_id ?? '');
    switch (ev.type) {
      case 'task.progress': {
        if (!sid) break;
        set({
          progress: { ...get().progress, [sid]: { progress: Number(p.progress ?? 0), stage: String(p.stage ?? '') } },
        });
        break;
      }
      case 'task.completed':
      case 'source.ready': {
        if (!sid) break;
        const { [sid]: _drop, ...progress } = get().progress;
        set({
          progress,
          repos: get().repos.map((r) => (r.id === sid ? { ...r, status: 'ready' as const } : r)),
        });
        break;
      }
      case 'task.failed': {
        if (!sid) break;
        const { [sid]: _drop, ...progress } = get().progress;
        set({
          progress,
          repos: get().repos.map((r) =>
            r.id === sid
              ? { ...r, status: 'failed' as const, error: String(p.error ?? '') }
              : r,
          ),
        });
        break;
      }
      case 'source.added': {
        // 新导入:立即刷新列表(importing 态可见)
        void get().reload().catch(() => {});
        break;
      }
      case 'source.removed': {
        set({ repos: get().repos.filter((r) => r.id !== sid) });
        break;
      }
      default:
        break;
    }
  },
}));
