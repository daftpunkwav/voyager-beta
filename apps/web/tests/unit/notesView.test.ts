import { afterEach, describe, expect, it } from 'vitest';
import { applyNotesSettingKey, applyNotesViewSnapshot } from '@/pages/notes/notesView';
import { useNotesUiStore } from '@/stores/notesUiStore';

afterEach(() => {
  useNotesUiStore.getState().apply({
    fontSize: 15,
    mode: 'edit',
    layout: 'list',
    listState: 'active',
    sort: 'updated',
    filter: 'all',
    query: '',
    sourceId: '',
    panel: 'none',
    density: 'comfortable',
    syncScroll: true,
    tocWidth: 188,
  });
});

describe('applyNotesViewSnapshot', () => {
  it('把后端笔记界面快照写入 store', () => {
    applyNotesViewSnapshot({
      font_size: 18,
      mode: 'preview',
      layout: 'card',
      sync_scroll: false,
      list_state: 'archived',
    });
    const s = useNotesUiStore.getState();
    expect(s.fontSize).toBe(18);
    expect(s.mode).toBe('preview');
    expect(s.layout).toBe('card');
    expect(s.syncScroll).toBe(false);
    expect(s.listState).toBe('archived');
  });

  it('写入筛选与排序', () => {
    applyNotesViewSnapshot({
      sort: 'created',
      filter: 'untitled',
      query: '架构',
      panel: 'trash',
      density: 'compact',
    });
    const s = useNotesUiStore.getState();
    expect(s.sort).toBe('created');
    expect(s.filter).toBe('untitled');
    expect(s.query).toBe('架构');
    expect(s.panel).toBe('trash');
    expect(s.density).toBe('compact');
  });

  it('写入目录宽度', () => {
    applyNotesViewSnapshot({ toc_width: 260 });
    expect(useNotesUiStore.getState().tocWidth).toBe(260);
    applyNotesSettingKey('notes.ui.toc_width', 80);
    expect(useNotesUiStore.getState().tocWidth).toBe(148);
  });

  it('settings.changed 单键写入,不碰全站字号键', () => {
    applyNotesSettingKey('notes.ui.font_size', 16);
    applyNotesSettingKey('appearance.font_scale', 1.2);
    expect(useNotesUiStore.getState().fontSize).toBe(16);
  });
});
