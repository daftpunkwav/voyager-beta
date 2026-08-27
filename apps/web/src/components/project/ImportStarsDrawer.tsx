import { useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { SelectReposEvent, StarRepo } from '@/api/types';
import { useGithubStars, useImportProjects, useProjects } from '@/hooks/useProjects';
import { useUIStore } from '@/stores/uiStore';
import {
  collectRepoLanguages,
  countImportStatus,
  DEFAULT_IMPORT_REPO_FILTER,
  filterAndSortStarRepos,
  type ImportRepoFilterState,
} from '@/utils/importRepoFilter';
import { ImportAgentModal } from './ImportAgentModal';
import { ImportRepoFilterBar } from './ImportRepoFilterBar';
import { EmbedAgentChat } from '@/components/agent/EmbedAgentChat';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';

interface ImportStarsDrawerProps {
  open: boolean;
  onClose: () => void;
}

function repoKey(s: Pick<StarRepo, 'owner' | 'repo'>): string {
  return `${s.owner}/${s.repo}`;
}

const GH_USER_KEY = 'voyager-github-username';

export function ImportStarsDrawer({ open, onClose }: ImportStarsDrawerProps) {
  const qc = useQueryClient();
  const [ghUser, setGhUser] = useState(() => localStorage.getItem(GH_USER_KEY) ?? '');
  const { data: starsResult, isLoading, isFetching } = useGithubStars({
    username: ghUser,
    enabled: open && Boolean(ghUser),
  });
  const { data: projectsPage } = useProjects();
  const importMutation = useImportProjects();
  const addToast = useUIStore((s) => s.addToast);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [refreshing, setRefreshing] = useState(false);
  const [agentAvailable, setAgentAvailable] = useState(true);
  const [filters, setFilters] = useState<ImportRepoFilterState>(
    DEFAULT_IMPORT_REPO_FILTER
  );

  // 兜底空数组包进 useMemo，避免每次渲染生成新引用导致下游 useMemo 依赖失稳;
  // already_imported 由本地已导入项目名合并(stars 原始数据无此标记)
  const importedNames = useMemo(
    () => new Set((projectsPage?.items ?? []).map((p) => p.name)),
    [projectsPage?.items],
  );
  const stars = useMemo(
    () => (starsResult?.items ?? []).map((s) => ({
      ...s,
      already_imported: importedNames.has(s.repo),
    })),
    [starsResult?.items, importedNames],
  );

  const filteredStars = useMemo(
    () => filterAndSortStarRepos(stars, filters),
    [stars, filters]
  );

  const languages = useMemo(() => collectRepoLanguages(stars), [stars]);
  const statusCounts = useMemo(() => countImportStatus(stars), [stars]);

  const selectableVisible = useMemo(
    () => filteredStars.filter((s) => !s.already_imported),
    [filteredStars]
  );

  useEffect(() => {
    if (!open) {
      setSelected(new Set());
      setFilters(DEFAULT_IMPORT_REPO_FILTER);
      setAgentAvailable(true);
    }
  }, [open]);

  // 切换筛选后，去掉已不可见或已导入的勾选，避免「已选 N」与列表脱节
  useEffect(() => {
    setSelected((prev) => {
      if (prev.size === 0) return prev;
      const visibleKeys = new Set(selectableVisible.map(repoKey));
      let changed = false;
      const next = new Set<string>();
      for (const k of prev) {
        if (visibleKeys.has(k)) next.add(k);
        else changed = true;
      }
      return changed ? next : prev;
    });
  }, [selectableVisible]);

  const repoKeys = useMemo(
    () => selectableVisible.map(repoKey),
    [selectableVisible]
  );

  const availableRepos = useMemo(
    () =>
      stars.map((s) => ({
        key: repoKey(s),
        language: s.language,
        stars: s.stars,
        already_imported: s.already_imported,
        description: s.description,
      })),
    [stars]
  );

  const importedProjects = useMemo(
    () =>
      (projectsPage?.items ?? []).map((p) => ({
        name: p.name,
        language: p.language,
        progress: p.progress,
        stars: p.stars,
        description: p.description,
      })),
    [projectsPage]
  );

  const filterSummary = useMemo(() => {
    const parts = [
      `显示 ${filteredStars.length}`,
      `共 ${statusCounts.total}`,
      `未导入 ${statusCounts.notImported}`,
      `已导入 ${statusCounts.imported}`,
    ];
    return parts.join(' · ');
  }, [filteredStars.length, statusCounts]);

  const toggle = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const selectVisible = () => {
    setSelected(new Set(selectableVisible.map(repoKey)));
  };

  const clearSelection = () => setSelected(new Set());

  const applyAgentSelection = (ev: SelectReposEvent) => {
    const allowed = new Set(stars.filter((s) => !s.already_imported).map(repoKey));
    setSelected((prev) => {
      const sanitize = (keys: string[]) => keys.filter((k) => allowed.has(k));
      if (ev.action === 'set') return new Set(sanitize(ev.repo_keys));
      if (ev.action === 'add') {
        const next = new Set(prev);
        for (const k of sanitize(ev.repo_keys)) next.add(k);
        return next;
      }
      const next = new Set(prev);
      for (const k of ev.repo_keys) next.delete(k);
      return next;
    });
  };

  const handleImport = async () => {
    const repos = stars
      .filter((s) => selected.has(repoKey(s)) && !s.already_imported)
      .map((s) => ({ owner: s.owner, repo: s.repo, url: s.url }));
    if (repos.length === 0) {
      addToast({ type: 'warning', message: '请选择未导入的项目' });
      return;
    }
    try {
      const result = await importMutation.mutateAsync(repos);
      addToast({ type: 'success', message: result.summary });
      onClose();
    } catch {
      addToast({ type: 'error', message: '导入失败' });
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const { getApi } = await import('@/api/client');
      const res = await getApi().listStars(ghUser);
      const total = (res.data as { total?: number; items?: unknown[] }).total
        ?? (res.data as { items?: unknown[] }).items?.length
        ?? 0;
      void qc.invalidateQueries({ queryKey: ['githubStars', ghUser] });
      addToast({
        type: 'success',
        message: `已刷新 ${total} 个 Stars`,
      });
    } catch {
      addToast({ type: 'error', message: '刷新 Stars 失败' });
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <ImportAgentModal
      open={open}
      onClose={onClose}
      title="同步 GitHub Stars"
      subtitle="左侧筛选并勾选仓库；右侧导入助手可自动勾选并说明推荐"
      agentPanel={
        agentAvailable ? (
          <EmbedAgentChat
            mode="import"
            title="导入助手"
            subtitle="智能勾选 · 说明清单"
            agentInitial="C"
            agentClassName="agent-curator"
            importContext={{
              mode: 'stars',
              available_repo_keys: repoKeys,
              selected_repo_keys: [...selected],
              available_repos: availableRepos,
              imported_projects: importedProjects,
            }}
            onSelectRepos={applyAgentSelection}
            onUnavailable={() => setAgentAvailable(false)}
          />
        ) : (
          <div className="embed-msg embed-msg--error" role="alert" data-testid="import-agent-down">
            导入助手不可用：Agent 服务未启用或不可用，请使用左侧手动勾选
          </div>
        )
      }
    >
      {!ghUser ? (
        <div className="import-biz-empty">
          <p>输入 GitHub 用户名以同步你的 Stars(只读公开数据,无需 PAT)。</p>
          <div className="import-biz-username">
            <input
              value={ghUser}
              placeholder="例如: torvalds"
              onChange={(e) => setGhUser(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && ghUser.trim()) {
                  localStorage.setItem(GH_USER_KEY, ghUser.trim());
                  setGhUser(ghUser.trim());
                }
              }}
            />
            <button
              type="button"
              className="btn btn-primary"
              disabled={!ghUser.trim()}
              onClick={() => localStorage.setItem(GH_USER_KEY, ghUser.trim())}
            >
              同步
            </button>
          </div>
        </div>
      ) : isLoading ? (
        <LoadingSpinner />
      ) : (
        <div className="import-biz-layout">
          <div className="import-biz-toolbar">
            <div className="import-biz-meta">
              <span className="muted">
                {starsResult?.total ?? stars.length} 个 Star
                {starsResult?.cached ? ' · 缓存' : ' · 实时'}
              </span>
              {starsResult?.fetched_at && (
                <span className="muted small">
                  更新于 {new Date(starsResult.fetched_at).toLocaleString('zh-CN')}
                </span>
              )}
            </div>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={isFetching || refreshing}
              onClick={() => void handleRefresh()}
            >
              {refreshing || isFetching ? '刷新中…' : '强制刷新'}
            </button>
          </div>

          <ImportRepoFilterBar
            value={filters}
            onChange={setFilters}
            languages={languages}
            summary={filterSummary}
            onSelectVisible={selectVisible}
            onClearSelection={clearSelection}
            selectVisibleDisabled={selectableVisible.length === 0}
            clearSelectionDisabled={selected.size === 0}
          />

          <ul className="import-repo-list import-repo-list--fill">
            {filteredStars.length === 0 ? (
              <li className="import-repo-empty">
                {stars.length === 0
                  ? '暂无 Star 仓库'
                  : '当前筛选下无结果，试试切换「全部」或清空关键字'}
              </li>
            ) : (
              filteredStars.map((s: StarRepo) => {
                const key = repoKey(s);
                const isOn = selected.has(key);
                return (
                  <li
                    key={key}
                    className={`import-repo-item ${isOn ? 'import-repo-item--selected' : ''}`}
                  >
                    <label>
                      <input
                        type="checkbox"
                        disabled={s.already_imported}
                        checked={isOn}
                        onChange={() => toggle(key)}
                      />
                      <span className="font-mono">{key}</span>
                      {s.language && <span className="badge">{s.language}</span>}
                      {typeof s.stars === 'number' && s.stars > 0 && (
                        <span className="import-repo-stars">★ {s.stars}</span>
                      )}
                      {s.already_imported && <span className="badge">已导入</span>}
                      {s.description && (
                        <span className="import-repo-desc">{s.description}</span>
                      )}
                    </label>
                  </li>
                );
              })
            )}
          </ul>
          <div className="import-biz-footer">
            <span className="muted">已选 {selected.size}</span>
            <button
              type="button"
              className="btn btn-primary"
              disabled={importMutation.isPending || selected.size === 0}
              onClick={() => void handleImport()}
            >
              {importMutation.isPending
                ? '导入中…'
                : `导入选中 (${selected.size})`}
            </button>
          </div>
        </div>
      )}
    </ImportAgentModal>
  );
}
