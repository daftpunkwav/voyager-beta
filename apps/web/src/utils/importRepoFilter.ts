/**
 * 导入 / Stars 同步列表的前端筛选与排序
 */
import type { StarRepo } from '@/api/types';

/** 导入状态筛选 */
export type ImportStatusFilter = 'all' | 'not_imported' | 'imported';

/** 排序方式 */
export type ImportSortBy = 'stars' | 'name' | 'language';

export interface ImportRepoFilterState {
  /** 关键字：匹配 owner/repo/description（大小写不敏感） */
  query: string;
  /** 语言；空字符串表示全部 */
  language: string;
  /** 是否已导入 */
  importStatus: ImportStatusFilter;
  sortBy: ImportSortBy;
}

export const DEFAULT_IMPORT_REPO_FILTER: ImportRepoFilterState = {
  query: '',
  language: '',
  // 默认排除已导入，减少噪音
  importStatus: 'not_imported',
  sortBy: 'stars',
};

export function collectRepoLanguages(items: StarRepo[]): string[] {
  const set = new Set<string>();
  for (const item of items) {
    const lang = item.language?.trim();
    if (lang) set.add(lang);
  }
  return [...set].sort((a, b) => a.localeCompare(b, 'en'));
}

function matchesQuery(item: StarRepo, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const hay = [
    item.owner,
    item.repo,
    `${item.owner}/${item.repo}`,
    item.description ?? '',
    item.url,
  ]
    .join(' ')
    .toLowerCase();
  return hay.includes(q);
}

function matchesImportStatus(item: StarRepo, status: ImportStatusFilter): boolean {
  if (status === 'all') return true;
  if (status === 'not_imported') return !item.already_imported;
  return item.already_imported;
}

function compareRepos(a: StarRepo, b: StarRepo, sortBy: ImportSortBy): number {
  if (sortBy === 'name') {
    const an = `${a.owner}/${a.repo}`.toLowerCase();
    const bn = `${b.owner}/${b.repo}`.toLowerCase();
    return an.localeCompare(bn, 'en');
  }
  if (sortBy === 'language') {
    const al = (a.language || '\uffff').toLowerCase();
    const bl = (b.language || '\uffff').toLowerCase();
    const byLang = al.localeCompare(bl, 'en');
    if (byLang !== 0) return byLang;
    return (b.stars ?? 0) - (a.stars ?? 0);
  }
  // stars 降序；相同则按名称
  const byStars = (b.stars ?? 0) - (a.stars ?? 0);
  if (byStars !== 0) return byStars;
  return `${a.owner}/${a.repo}`.localeCompare(`${b.owner}/${b.repo}`, 'en');
}

/** 筛选并排序 Star / 搜索结果列表 */
export function filterAndSortStarRepos(
  items: StarRepo[],
  filters: ImportRepoFilterState
): StarRepo[] {
  const language = filters.language.trim();
  const filtered = items.filter((item) => {
    if (!matchesImportStatus(item, filters.importStatus)) return false;
    if (language && (item.language || '') !== language) return false;
    if (!matchesQuery(item, filters.query)) return false;
    return true;
  });
  return filtered.slice().sort((a, b) => compareRepos(a, b, filters.sortBy));
}

/** 统计原始列表中的已导入 / 未导入数量 */
export function countImportStatus(items: StarRepo[]): {
  total: number;
  imported: number;
  notImported: number;
} {
  let imported = 0;
  for (const item of items) {
    if (item.already_imported) imported += 1;
  }
  return {
    total: items.length,
    imported,
    notImported: items.length - imported,
  };
}
