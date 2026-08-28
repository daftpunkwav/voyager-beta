/** 笔记清单:摘要、关联源、筛选/排序/按日分段。 */

import { formatRelativeTime } from '@/utils/date';
import type { NotesFilter, NotesSort } from './notePrefs';

const PLACEHOLDER_TITLE = /^(新笔记|无标题|untitled|草稿)(\s|$)/i;

type NoteListItem = {
  title?: string;
  pinned?: boolean;
  updated_ts?: number;
  updated_at?: string;
  created_ts?: number;
  created_at?: string | number;
  project_id?: string;
  source_id?: string;
  excerpt?: string;
  content?: string;
};

/** 缺省标题,agent 连发新建时用来筛出未起名的篇。 */
export function isPlaceholderTitle(title: string | undefined): boolean {
  const t = (title || '').trim();
  if (!t) return true;
  return PLACEHOLDER_TITLE.test(t);
}

export function startOfLocalDayMs(now = Date.now()): number {
  const d = new Date(now);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

/** 后端 list/get 用 source_id;旧前端字段是 project_id */
export function noteSourceId(n: { project_id?: string; source_id?: string }): string {
  return n.project_id || n.source_id || '';
}

/** list_notes 只回 excerpt,没有 content;全文接口才有 content */
export function noteSnippet(n: { excerpt?: string; content?: string }): string {
  return (n.excerpt || n.content || '').replace(/[#*`]/g, '').replace(/\s+/g, ' ').trim();
}

function epochToMs(ts?: number, fallback?: string | number): number {
  if (typeof ts === 'number' && ts > 0) {
    return ts < 1e12 ? ts * 1000 : ts;
  }
  if (typeof fallback === 'number' && fallback > 0) {
    return fallback < 1e12 ? fallback * 1000 : fallback;
  }
  if (typeof fallback === 'string' && fallback) {
    return Date.parse(fallback) || 0;
  }
  return 0;
}

type NoteTimestamps = {
  updated_at?: string;
  updated_ts?: number;
  created_at?: string | number;
  created_ts?: number;
};

/** 统一成毫秒。后端 updated_ts 多为秒;updated_at 为 ISO。 */
export function noteUpdatedMs(n: NoteTimestamps): number {
  return epochToMs(n.updated_ts, n.updated_at);
}

export function noteCreatedMs(n: NoteTimestamps): number {
  const ms = epochToMs(n.created_ts, n.created_at);
  return ms > 0 ? ms : noteUpdatedMs(n);
}

export function noteUpdatedLabel(n: NoteTimestamps): string {
  if (n.updated_at) return formatRelativeTime(n.updated_at);
  const ms = noteUpdatedMs(n);
  if (ms > 0) return formatRelativeTime(new Date(ms).toISOString());
  return '';
}

export interface NotesListingOpts<T = NoteListItem> {
  query?: string;
  filter?: NotesFilter;
  sort?: NotesSort;
  sourceId?: string;
  extraText?: (n: T) => string;
}

/** 置顶始终在前;其余按最近改 / 最近建 / 标题。 */
export function sortNotes<T extends NoteListItem>(notes: T[], sort: NotesSort): T[] {
  return [...notes].sort((a, b) => {
    const pin = Number(Boolean(b.pinned)) - Number(Boolean(a.pinned));
    if (pin !== 0) return pin;
    if (sort === 'title') {
      return (a.title || '').localeCompare(b.title || '', 'zh');
    }
    if (sort === 'created') {
      return noteCreatedMs(b) - noteCreatedMs(a);
    }
    return noteUpdatedMs(b) - noteUpdatedMs(a);
  });
}

export function filterNotes<T extends NoteListItem>(notes: T[], filter: NotesFilter, now = Date.now()): T[] {
  if (filter === 'all') return notes;
  if (filter === 'pinned') return notes.filter((n) => Boolean(n.pinned));
  if (filter === 'untitled') return notes.filter((n) => isPlaceholderTitle(n.title));
  if (filter === 'unlinked') return notes.filter((n) => !noteSourceId(n));
  const start = startOfLocalDayMs(now);
  return notes.filter((n) => noteCreatedMs(n) >= start);
}

/** 首页清单:关联 → 关键词 → 筛选 → 排序。纯函数,页面与 agent 快照共用。 */
export function applyNotesListing<T extends NoteListItem>(notes: T[], opts: NotesListingOpts<T>, now = Date.now()): T[] {
  const sourceId = opts.sourceId || '';
  const q = (opts.query || '').trim().toLowerCase();
  let out = notes;
  if (sourceId) out = out.filter((n) => noteSourceId(n) === sourceId);
  if (q) {
    out = out.filter((n) => {
      const title = (n.title || '').toLowerCase();
      const snippet = noteSnippet(n).toLowerCase();
      const extra = (opts.extraText?.(n) ?? '').toLowerCase();
      return title.includes(q) || snippet.includes(q) || extra.includes(q);
    });
  }
  out = filterNotes(out, opts.filter ?? 'all', now);
  return sortNotes(out, opts.sort ?? 'updated');
}

export interface NotesBucket<T> {
  id: string;
  label: string;
  items: T[];
}

/** 列表按日分段,agent 短时间连建时便于扫。标题排序不分段。 */
export function groupNotesByRecency<T extends NoteListItem>(
  notes: T[],
  by: 'updated' | 'created',
  now = Date.now(),
): NotesBucket<T>[] {
  const start = startOfLocalDayMs(now);
  const yesterday = start - 86_400_000;
  const week = start - 6 * 86_400_000;
  const buckets: Record<string, T[]> = {
    today: [],
    yesterday: [],
    week: [],
    older: [],
  };
  for (const n of notes) {
    const ms = by === 'created' ? noteCreatedMs(n) : noteUpdatedMs(n);
    if (ms >= start) buckets.today.push(n);
    else if (ms >= yesterday) buckets.yesterday.push(n);
    else if (ms >= week) buckets.week.push(n);
    else buckets.older.push(n);
  }
  const labels: Record<string, string> = {
    today: '今日',
    yesterday: '昨日',
    week: '近 7 天',
    older: '更早',
  };
  return (['today', 'yesterday', 'week', 'older'] as const)
    .filter((id) => buckets[id].length > 0)
    .map((id) => ({ id, label: labels[id], items: buckets[id] }));
}
