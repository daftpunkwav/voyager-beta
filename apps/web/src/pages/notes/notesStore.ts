/** 笔记状态:摘要列表(服务端 excerpt)与全文缓存分离;排序本地做。 */

import { create } from 'zustand';
import { callCapability, ServiceError } from '@/bridge/client';

export interface NoteSummary {
  id: string;
  title: string;
  tags: string[];
  source_id: string;
  node_id: string;
  created_ts: number;
  updated_ts: number;
  excerpt: string; // 服务端 120 字摘要,列表永不请求全文
}

export interface Note extends NoteSummary {
  content: string;
}

export type NoteSort = 'updated' | 'created' | 'title';

interface NotesState {
  summaries: NoteSummary[];
  current: Note | null;
  /** 本地全文缓存(已打开过的笔记),open 优先命中 */
  cache: Record<string, Note>;
  filterTag: string;
  sort: NoteSort;
  pageSize: number;
  autosaveS: number;
  loading: boolean;
  error: { code: string; message: string } | null;
  init: () => Promise<void>; // 设置键 + 摘要列表
  open: (id: string) => Promise<void>;
  create: () => Promise<void>;
  save: (id: string, patch: { title?: string; content?: string; tags?: string[] }) => Promise<Note>;
  remove: (id: string) => Promise<void>;
  link: (id: string, source_id?: string, node_id?: string) => Promise<void>;
  setFilterTag: (tag: string) => void;
}

function sortSummaries(list: NoteSummary[], sort: NoteSort): NoteSummary[] {
  const copy = [...list];
  if (sort === 'title') copy.sort((a, b) => a.title.localeCompare(b.title));
  else if (sort === 'created') copy.sort((a, b) => b.created_ts - a.created_ts);
  else copy.sort((a, b) => b.updated_ts - a.updated_ts);
  return copy;
}

export const useNotesStore = create<NotesState>((set, get) => ({
  summaries: [],
  current: null,
  cache: {},
  filterTag: '',
  sort: 'updated',
  pageSize: 100,
  autosaveS: 5,
  loading: false,
  error: null,

  init: async () => {
    set({ loading: true, error: null });
    try {
      const [sortItem, sizeItem, autosaveItem, summaries] = await Promise.all([
        callCapability<{ value: string }>('settings', 'get_setting', {
          key: 'notes.sort.default',
        }),
        callCapability<{ value: number }>('settings', 'get_setting', {
          key: 'notes.list.page_size',
        }),
        callCapability<{ value: number }>('settings', 'get_setting', {
          key: 'notes.editor.autosave_s',
        }),
        callCapability<NoteSummary[]>('notes', 'list_notes', { limit: 500 }),
      ]);
      set({
        sort: (sortItem.value as NoteSort) ?? 'updated',
        pageSize: sizeItem.value ?? 100,
        autosaveS: autosaveItem.value ?? 5,
        summaries,
        loading: false,
      });
    } catch (err) {
      const e = err as ServiceError;
      set({ loading: false, error: { code: e.code, message: e.message } });
    }
  },

  open: async (id) => {
    const cached = get().cache[id];
    if (cached) {
      set({ current: cached });
      return;
    }
    const note = await callCapability<Note>('notes', 'get_note', { note_id: id });
    set({ current: note, cache: { ...get().cache, [id]: note } });
  },

  create: async () => {
    const note = await callCapability<Note>('notes', 'create_note', {
      title: '未命名笔记',
    });
    set({
      summaries: [note, ...get().summaries],
      current: note,
      cache: { ...get().cache, [note.id]: note },
    });
  },

  save: async (id, patch) => {
    const note = await callCapability<Note>('notes', 'update_note', {
      note_id: id,
      ...patch,
    });
    set({
      current: note,
      cache: { ...get().cache, [id]: note },
      summaries: get().summaries.map((s) =>
        s.id === id
          ? {
              ...s,
              title: note.title,
              tags: note.tags,
              updated_ts: note.updated_ts,
            }
          : s,
      ),
    });
    return note;
  },

  remove: async (id) => {
    await callCapability('notes', 'delete_note', { note_id: id });
    const { [id]: _drop, ...cache } = get().cache;
    set({
      summaries: get().summaries.filter((s) => s.id !== id),
      cache,
      current: get().current?.id === id ? null : get().current,
    });
  },

  link: async (id, source_id, node_id) => {
    const note = await callCapability<Note>('notes', 'link_note', {
      note_id: id,
      source_id,
      node_id,
    });
    set({
      current: note,
      cache: { ...get().cache, [id]: note },
    });
  },

  setFilterTag: (tag) => set({ filterTag: tag }),
}));

/** 列表视图数据:标签过滤 + 本地排序(不新增服务端能力)。 */
export function visibleSummaries(state: {
  summaries: NoteSummary[];
  filterTag: string;
  sort: NoteSort;
}): NoteSummary[] {
  const filtered = state.filterTag
    ? state.summaries.filter((s) => s.tags.includes(state.filterTag))
    : state.summaries;
  return sortSummaries(filtered, state.sort);
}
