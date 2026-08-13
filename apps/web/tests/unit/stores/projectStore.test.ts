import { describe, expect, it } from 'vitest';
import { beforeEach } from 'vitest';
import { useProjectStore } from '@/stores/projectStore';

describe('projectStore', () => {
  beforeEach(() => {
    useProjectStore.setState({
      search: '',
      categoryId: null,
      language: null,
      progress: null,
      tagId: null,
      sortBy: 'imported_at',
      sortOrder: 'desc',
      page: 1,
      pageSize: 20,
      selectedIds: [],
    });
  });

  it('setSearch resets page and selection', () => {
    useProjectStore.setState({ page: 5, selectedIds: ['p1', 'p2'] });
    useProjectStore.getState().setSearch('react');
    const s = useProjectStore.getState();
    expect(s.search).toBe('react');
    expect(s.page).toBe(1);
    expect(s.selectedIds).toEqual([]);
  });

  it('toggleSelected adds then removes', () => {
    const { toggleSelected } = useProjectStore.getState();
    toggleSelected('p1');
    expect(useProjectStore.getState().selectedIds).toEqual(['p1']);
    toggleSelected('p1');
    expect(useProjectStore.getState().selectedIds).toEqual([]);
  });

  it('resetFilters restores defaults', () => {
    useProjectStore.setState({ search: 'x', page: 9, selectedIds: ['p1'] });
    useProjectStore.getState().resetFilters();
    const s = useProjectStore.getState();
    expect(s.search).toBe('');
    expect(s.page).toBe(1);
    expect(s.sortBy).toBe('imported_at');
    expect(s.sortOrder).toBe('desc');
    expect(s.selectedIds).toEqual([]);
  });

  it('toApiParams maps nulls to undefined', () => {
    useProjectStore.setState({
      search: '  react  ',
      categoryId: 'cat_x',
      language: null,
    });
    const api = useProjectStore.getState().toApiParams();
    expect(api.search).toBe('  react  ');
    expect(api.category_id).toBe('cat_x');
    expect(api.language).toBeUndefined();
  });
});
