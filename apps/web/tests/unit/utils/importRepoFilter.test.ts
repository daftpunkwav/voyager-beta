import { describe, expect, it } from 'vitest';
import type { StarRepo } from '@/api/types';
import {
  collectRepoLanguages,
  countImportStatus,
  DEFAULT_IMPORT_REPO_FILTER,
  filterAndSortStarRepos,
  type ImportRepoFilterState,
} from '@/utils/importRepoFilter';

function repo(
  partial: Partial<StarRepo> & Pick<StarRepo, 'owner' | 'repo'>
): StarRepo {
  return {
    url: `https://github.com/${partial.owner}/${partial.repo}`,
    description: partial.description,
    language: partial.language,
    stars: partial.stars ?? 0,
    already_imported: partial.already_imported ?? false,
    owner: partial.owner,
    repo: partial.repo,
  };
}

const sample: StarRepo[] = [
  repo({
    owner: 'vercel',
    repo: 'next.js',
    language: 'JavaScript',
    stars: 1000,
    already_imported: true,
    description: 'React framework',
  }),
  repo({
    owner: 'facebook',
    repo: 'react',
    language: 'JavaScript',
    stars: 2000,
    already_imported: false,
    description: 'UI library',
  }),
  repo({
    owner: 'rust-lang',
    repo: 'rust',
    language: 'Rust',
    stars: 1500,
    already_imported: false,
  }),
];

describe('importRepoFilter', () => {
  it('默认排除已导入', () => {
    const out = filterAndSortStarRepos(sample, DEFAULT_IMPORT_REPO_FILTER);
    expect(out.map((r) => r.repo)).toEqual(['react', 'rust']);
  });

  it('可显示全部并按 stars 降序', () => {
    const filters: ImportRepoFilterState = {
      ...DEFAULT_IMPORT_REPO_FILTER,
      importStatus: 'all',
      sortBy: 'stars',
    };
    const out = filterAndSortStarRepos(sample, filters);
    expect(out.map((r) => r.repo)).toEqual(['react', 'rust', 'next.js']);
  });

  it('按语言筛选', () => {
    const out = filterAndSortStarRepos(sample, {
      ...DEFAULT_IMPORT_REPO_FILTER,
      importStatus: 'all',
      language: 'Rust',
    });
    expect(out).toHaveLength(1);
    expect(out[0].repo).toBe('rust');
  });

  it('关键字匹配 owner/repo/description', () => {
    const out = filterAndSortStarRepos(sample, {
      ...DEFAULT_IMPORT_REPO_FILTER,
      importStatus: 'all',
      query: 'framework',
    });
    expect(out.map((r) => r.repo)).toEqual(['next.js']);
  });

  it('仅已导入', () => {
    const out = filterAndSortStarRepos(sample, {
      ...DEFAULT_IMPORT_REPO_FILTER,
      importStatus: 'imported',
    });
    expect(out.map((r) => r.repo)).toEqual(['next.js']);
  });

  it('collectRepoLanguages 去重排序', () => {
    expect(collectRepoLanguages(sample)).toEqual(['JavaScript', 'Rust']);
  });

  it('countImportStatus 统计', () => {
    expect(countImportStatus(sample)).toEqual({
      total: 3,
      imported: 1,
      notImported: 2,
    });
  });
});
