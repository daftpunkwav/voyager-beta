// @ts-nocheck — 迁移期:RepoPilot 风格代码,新 page / hook 仍按 strict 写(见各文件顶部注释)。
import { useEffect, useMemo, useState } from 'react';
import type { Category, Project, Tag } from '@/api/types';
import { useProjectStore } from '@/stores/projectStore';
import { FilterDropdown } from './FilterDropdown';

interface FilterBarProps {
  categories: Category[];
  tags: Tag[];
  languages: string[];
}

export function FilterBar({ categories, tags, languages }: FilterBarProps) {
  const search = useProjectStore((s) => s.search);
  const setSearch = useProjectStore((s) => s.setSearch);
  const categoryId = useProjectStore((s) => s.categoryId);
  const setCategoryId = useProjectStore((s) => s.setCategoryId);
  const language = useProjectStore((s) => s.language);
  const setLanguage = useProjectStore((s) => s.setLanguage);
  const progress = useProjectStore((s) => s.progress);
  const setProgress = useProjectStore((s) => s.setProgress);
  const tagId = useProjectStore((s) => s.tagId);
  const setTagId = useProjectStore((s) => s.setTagId);
  const sortBy = useProjectStore((s) => s.sortBy);
  const setSortBy = useProjectStore((s) => s.setSortBy);
  const resetFilters = useProjectStore((s) => s.resetFilters);
  const [localSearch, setLocalSearch] = useState(search);

  useEffect(() => {
    const t = setTimeout(() => setSearch(localSearch), 300);
    return () => clearTimeout(t);
  }, [localSearch, setSearch]);

  const langs = useMemo(() => {
    if (languages.length > 0) return languages;
    return [];
  }, [languages]);

  const hasActiveFilter = Boolean(
    categoryId || language || progress || tagId || localSearch
  );

  const categoryOptions = useMemo(
    () => [
      { value: '', label: '全部' },
      ...categories.map((c) => ({ value: c.id, label: c.name })),
    ],
    [categories]
  );

  const languageOptions = useMemo(
    () => [
      { value: '', label: '全部' },
      ...langs.map((l) => ({ value: l, label: l })),
    ],
    [langs]
  );

  const progressOptions = useMemo(
    () => [
      { value: '', label: '全部' },
      { value: 'none', label: '待开始' },
      { value: 'learning', label: '学习中' },
      { value: 'learned', label: '已学习' },
      { value: 'mastered', label: '已掌握' },
    ],
    []
  );

  const tagOptions = useMemo(
    () => [
      { value: '', label: '全部' },
      ...tags.map((t) => ({ value: t.id, label: t.name })),
    ],
    [tags]
  );

  const sortOptions = useMemo(
    () => [
      { value: 'updated_at', label: '最近更新' },
      { value: 'imported_at', label: '导入时间' },
      { value: 'stars', label: 'Stars' },
      { value: 'name', label: '名称' },
    ],
    []
  );

  return (
    <div className="filter-bar glass-card glass-card--overview-outer glass-overflow-visible" role="toolbar" aria-label="项目筛选">
      <div className="filter-search">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={14} height={14}>
          <circle cx="11" cy="11" r="7" />
          <path d="M21 21l-4.3-4.3" />
        </svg>
        <input
          type="text"
          placeholder="筛选当前列表：项目名 / 描述 / 标签"
          value={localSearch}
          onChange={(e) => setLocalSearch(e.target.value)}
        />
      </div>

      <FilterDropdown
        prefix="分类："
        value={categoryId ?? ''}
        options={categoryOptions}
        onChange={(v) => setCategoryId(v || null)}
        active={Boolean(categoryId)}
        ariaLabel="分类筛选"
      />

      <FilterDropdown
        prefix="语言："
        value={language ?? ''}
        options={languageOptions}
        onChange={(v) => setLanguage(v || null)}
        active={Boolean(language)}
        ariaLabel="语言筛选"
      />

      <FilterDropdown
        prefix="进度："
        value={progress ?? ''}
        options={progressOptions}
        onChange={(v) => setProgress((v || null) as Project['progress'] | null)}
        active={Boolean(progress)}
        ariaLabel="进度筛选"
      />

      <FilterDropdown
        prefix="标签："
        value={tagId ?? ''}
        options={tagOptions}
        onChange={(v) => setTagId(v || null)}
        active={Boolean(tagId)}
        ariaLabel="标签筛选"
      />

      <div className="filter-dropdown filter-dropdown--sort">
        <FilterDropdown
          prefix="排序："
          value={sortBy}
          options={sortOptions}
          onChange={(v) =>
            setSortBy(v as 'name' | 'stars' | 'imported_at' | 'updated_at')
          }
          active={sortBy !== 'imported_at'}
          ariaLabel="排序"
        />
      </div>

      {hasActiveFilter && (
        <button type="button" className="filter-clear" onClick={resetFilters}>
          清除筛选
        </button>
      )}
    </div>
  );
}

export function useProjectLanguages(projects: Project[]): string[] {
  return useMemo(() => {
    const set = new Set<string>();
    for (const p of projects) {
      if (p.language) set.add(p.language);
    }
    return Array.from(set).sort();
  }, [projects]);
}
