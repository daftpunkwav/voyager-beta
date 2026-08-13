import { describe, expect, it, beforeEach } from 'vitest';
import { useGraphStore } from '@/stores/graphStore';

describe('graphStore', () => {
  beforeEach(() => {
    useGraphStore.setState({
      selectedNodeId: null,
      highlightNodeId: null,
      searchQuery: '',
      minSimilarity: 0.1,
      maxEdges: 500,
      categoryFilter: null,
      zoomLevel: 1.0,
    });
  });

  it('clamp minSimilarity into [0, 1]', () => {
    useGraphStore.getState().setMinSimilarity(5);
    expect(useGraphStore.getState().minSimilarity).toBe(1);
    useGraphStore.getState().setMinSimilarity(-1);
    expect(useGraphStore.getState().minSimilarity).toBe(0);
  });

  it('clamp maxEdges into [10, 1000]', () => {
    useGraphStore.getState().setMaxEdges(99999);
    expect(useGraphStore.getState().maxEdges).toBe(1000);
    useGraphStore.getState().setMaxEdges(0);
    expect(useGraphStore.getState().maxEdges).toBe(10);
  });

  it('resetView keeps minSimilarity/maxEdges/categoryFilter', () => {
    useGraphStore.setState({ minSimilarity: 0.5, maxEdges: 999, zoomLevel: 2.0 });
    useGraphStore.getState().resetView();
    const s = useGraphStore.getState();
    expect(s.zoomLevel).toBe(1.0);
    expect(s.minSimilarity).toBe(0.5);
    expect(s.maxEdges).toBe(999);
  });
});
