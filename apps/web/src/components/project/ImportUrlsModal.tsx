import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getApi } from '@/api/client';
import type { SelectReposEvent, StarRepo } from '@/api/types';
import { useCreateProject, useImportProjects, useProjects } from '@/hooks/useProjects';
import { useUIStore } from '@/stores/uiStore';
import { validateGithubUrls } from '@/utils/validators';
import {
  collectRepoLanguages,
  countImportStatus,
  DEFAULT_IMPORT_REPO_FILTER,
  filterAndSortStarRepos,
  type ImportRepoFilterState,
} from '@/utils/importRepoFilter';
import { ImportAgentModal } from './ImportAgentModal';
import { ImportRepoFilterBar } from './ImportRepoFilterBar';
import { EmbedAgentChat } from '@/widgets/EmbedAgentChat';

type ImportTab = 'paste' | 'search';

interface ImportUrlsModalProps {
  open: boolean;
  onClose: () => void;
}

function repoKey(s: Pick<StarRepo, 'owner' | 'repo'>): string {
  return `${s.owner}/${s.repo}`;
}

export function ImportUrlsModal({ open, onClose }: ImportUrlsModalProps) {
  const [tab, setTab] = useState<ImportTab>('paste');
  const [text, setText] = useState('');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filters, setFilters] = useState<ImportRepoFilterState>(
    DEFAULT_IMPORT_REPO_FILTER
  );
  const [agentAvailable, setAgentAvailable] = useState(true);
  const importMutation = useImportProjects();
  const createMutation = useCreateProject();
  const { data: projectsPage } = useProjects();
  const addToast = useUIStore((s) => s.addToast);

  const { data: searchResults = [], isFetching } = useQuery({
    queryKey: ['githubSearch', search],
    queryFn: async () => (await getApi().searchGithubRepos(search)).data,
    enabled: open && tab === 'search' && search.trim().length >= 2,
  });

  const filteredResults = useMemo(
    () => filterAndSortStarRepos(searchResults, filters),
    [searchResults, filters]
  );

  const languages = useMemo(
    () => collectRepoLanguages(searchResults),
    [searchResults]
  );
  const statusCounts = useMemo(
    () => countImportStatus(searchResults),
    [searchResults]
  );

  const selectableVisible = useMemo(
    () => filteredResults.filter((s) => !s.already_imported),
    [filteredResults]
  );

  useEffect(() => {
    if (!open) {
      setText('');
      setSearch('');
      setSelected(new Set());
      setTab('paste');
      setFilters(DEFAULT_IMPORT_REPO_FILTER);
      setAgentAvailable(true);
    }
  }, [open]);

  // 切换筛选后清理不可见勾选
  useEffect(() => {
    if (tab !== 'search') return;
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
  }, [selectableVisible, tab]);

  if (!open) return null;

  const { valid, invalid } = validateGithubUrls(text);

  const filterSummary = [
    `显示 ${filteredResults.length}`,
    `共 ${statusCounts.total}`,
    `未导入 ${statusCounts.notImported}`,
    `已导入 ${statusCounts.imported}`,
  ].join(' · ');

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
    const allowed =
      tab === 'search'
        ? new Set(searchResults.filter((s) => !s.already_imported).map(repoKey))
        : new Set(valid.map((v) => v.name));
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

  const importRepos = async (repos: Array<{ owner: string; repo: string; url: string }>) => {
    if (repos.length === 0) {
      addToast({ type: 'warning', message: '请选择要导入的项目' });
      return;
    }
    try {
      const result = await importMutation.mutateAsync(repos);
      addToast({ type: 'success', message: result.summary });
      onClose();
    } catch {
      let ok = 0;
      for (const v of repos) {
        try {
          await createMutation.mutateAsync({
            name: `${v.owner}/${v.repo}`,
            url: v.url,
          });
          ok += 1;
        } catch (err) {
          // 失败明细留痕:重复/网络错/校验错都被计入"成功 N 条"之外的沉默区
          console.warn('[ImportUrlsModal] 条目导入失败:', v.url, err);
        }
      }
      addToast({ type: ok > 0 ? 'success' : 'error', message: `成功 ${ok} 条` });
      if (ok > 0) onClose();
    }
  };

  const handlePasteImport = () =>
    void importRepos(valid.map((v) => ({ owner: v.owner, repo: v.repo, url: v.url })));

  const handleSearchImport = () => {
    const repos = searchResults
      .filter((s) => selected.has(repoKey(s)) && !s.already_imported)
      .map((s) => ({ owner: s.owner, repo: s.repo, url: s.url }));
    void importRepos(repos);
  };

  const availableKeys =
    tab === 'search'
      ? selectableVisible.map(repoKey)
      : valid.map((v) => v.name);

  const availableRepos =
    tab === 'search'
      ? searchResults.map((s) => ({
          key: repoKey(s),
          language: s.language,
          stars: s.stars,
          already_imported: s.already_imported,
          description: s.description,
        }))
      : valid.map((v) => ({
          key: v.name,
          language: null,
          stars: 0,
          already_imported: false,
          description: null,
        }));

  const importedProjects = (projectsPage?.items ?? []).map((p) => ({
    name: p.name,
    language: p.language,
    progress: p.progress,
    stars: p.stars,
    description: p.description,
  }));

  return (
    <ImportAgentModal
      open={open}
      onClose={onClose}
      title="导入项目"
      subtitle="粘贴地址或搜索筛选；右侧助手可自动勾选并说明"
      size="large"
      agentPanel={
        agentAvailable ? (
          <EmbedAgentChat
            mode="import"
            title="导入助手"
            subtitle="智能勾选 · Stars/库内对比"
            agentInitial="S"
            agentClassName="agent-recon"
            importContext={{
              mode: tab === 'search' ? 'search' : 'urls',
              available_repo_keys: availableKeys,
              selected_repo_keys: [...selected],
              available_repos: availableRepos,
              imported_projects: importedProjects,
            }}
            onSelectRepos={applyAgentSelection}
            onUnavailable={() => setAgentAvailable(false)}
          />
        ) : (
          <div className="embed-msg embed-msg--error" role="alert" data-testid="import-agent-down">
            导入助手不可用：Agent 服务未启用或不可用，请使用左侧手动导入
          </div>
        )
      }
    >
      <div className="import-biz-layout">
        <div className="import-tabs">
          <button
            type="button"
            className={`import-tab ${tab === 'paste' ? 'active' : ''}`}
            onClick={() => setTab('paste')}
          >
            粘贴地址
          </button>
          <button
            type="button"
            className={`import-tab ${tab === 'search' ? 'active' : ''}`}
            onClick={() => setTab('search')}
          >
            搜索导入
          </button>
        </div>

        {tab === 'paste' ? (
          <>
            <p className="import-hint">
              每行一个 URL，支持多个仓库（后端将解析并批量导入）
            </p>
            <textarea
              className="input textarea import-url-textarea"
              rows={10}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="https://github.com/owner/repo"
            />
            <p className="import-hint">
              有效 {valid.length} 行，无效 {invalid.length} 行
            </p>
            <div className="import-biz-footer">
              <span className="muted">有效 {valid.length}</span>
              <button
                type="button"
                className="btn btn-primary"
                disabled={importMutation.isPending || valid.length === 0}
                onClick={handlePasteImport}
              >
                确认导入
              </button>
            </div>
          </>
        ) : (
          <>
            <label className="graph-search import-search-field">
              <input
                placeholder="搜索 GitHub 仓库…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            {isFetching && <p className="muted">搜索中…</p>}

            {searchResults.length > 0 && (
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
            )}

            <ul className="import-repo-list import-repo-list--fill">
              {search.trim().length < 2 ? (
                <li className="import-repo-empty">输入至少 2 个字符开始搜索</li>
              ) : isFetching && searchResults.length === 0 ? (
                <li className="import-repo-empty">搜索中…</li>
              ) : searchResults.length === 0 ? (
                <li className="import-repo-empty">未找到匹配仓库</li>
              ) : filteredResults.length === 0 ? (
                <li className="import-repo-empty">
                  当前筛选下无结果，试试切换「全部」或调整语言/关键字
                </li>
              ) : (
                filteredResults.map((s: StarRepo) => {
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
                        {s.already_imported && (
                          <span className="badge">已导入</span>
                        )}
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
                onClick={handleSearchImport}
              >
                {importMutation.isPending
                  ? '导入中…'
                  : `导入选中 (${selected.size})`}
              </button>
            </div>
          </>
        )}
      </div>
    </ImportAgentModal>
  );
}
