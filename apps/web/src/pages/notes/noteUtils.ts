/** 笔记页纯函数:偏好 / 源 ID / 行前缀 / 时间标签。不依赖 React。 */

import { formatRelativeTime } from '@/utils/date';
import { NOTE_HL_KIND } from './noteMarks';

export const NOTES_MODE_KEY = 'notes-mode';
export const NOTES_LAYOUT_KEY = 'notes-layout';
export const NOTES_SPLIT_KEY = 'notes-split';
export const NOTES_FONT_KEY = 'notes-font';
export const NOTES_SYNC_KEY = 'notes-sync-scroll';
export const NOTES_LIST_KEY = 'notes-list-state';
export const NOTES_SORT_KEY = 'notes-sort';
export const NOTES_FILTER_KEY = 'notes-filter';
export const NOTES_QUERY_KEY = 'notes-query';
export const NOTES_SOURCE_KEY = 'notes-source';
export const NOTES_PANEL_KEY = 'notes-panel';
export const NOTES_DENSITY_KEY = 'notes-density';
export const NOTES_TOC_WIDTH_KEY = 'notes-toc-width';

export const NOTES_FONT_MIN = 12;
export const NOTES_FONT_MAX = 24;
export const NOTES_FONT_DEFAULT = 15;
export const NOTES_TOC_WIDTH_MIN = 148;
export const NOTES_TOC_WIDTH_MAX = 480;
export const NOTES_TOC_WIDTH_DEFAULT = 188;

export type NotesMode = 'edit' | 'preview' | 'split';
export type NotesLayout = 'list' | 'card';
export type NotesListState = 'active' | 'archived';
export type NotesSort = 'updated' | 'created' | 'title';
export type NotesFilter = 'all' | 'pinned' | 'untitled' | 'unlinked' | 'today';
export type NotesPanel = 'none' | 'trash';
export type NotesDensity = 'comfortable' | 'compact';

export const NOTES_SORT_OPTIONS: { value: NotesSort; label: string }[] = [
  { value: 'updated', label: '最近改' },
  { value: 'created', label: '最近建' },
  { value: 'title', label: '标题' },
];

export const NOTES_FILTER_OPTIONS: { value: NotesFilter; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'pinned', label: '置顶' },
  { value: 'untitled', label: '草稿标题' },
  { value: 'unlinked', label: '未关联' },
  { value: 'today', label: '今日' },
];

const PLACEHOLDER_TITLE = /^(新笔记|无标题|untitled|草稿)(\s|$)/i;
const QUERY_MAX = 80;
const SOURCE_MAX = 80;
export const NOTES_QUOTE_MAX = 500;

/** 新建草稿 id 为 'new';其余(UUID / mock n_*)均视为已有笔记 */
export function isPersistedNoteId(id: string | null | undefined): id is string {
  return Boolean(id && id !== 'new');
}

export function parseNotesMode(modeRaw: string | null | undefined): NotesMode {
  if (modeRaw === 'edit' || modeRaw === 'preview' || modeRaw === 'split') return modeRaw;
  return 'edit';
}

export function parseNotesLayout(raw: string | null | undefined): NotesLayout {
  return raw === 'card' ? 'card' : 'list';
}

export function parseNotesListState(raw: string | null | undefined): NotesListState {
  return raw === 'archived' ? 'archived' : 'active';
}

export function parseSplitRatio(raw: string | null | undefined): number {
  const n = Number(raw);
  if (!Number.isFinite(n)) return 0.55;
  return Math.min(0.72, Math.max(0.32, n));
}

export function parseNotesFontSize(raw: string | null | undefined): number {
  if (raw == null || raw === '') return NOTES_FONT_DEFAULT;
  const n = Number(raw);
  if (!Number.isFinite(n)) return NOTES_FONT_DEFAULT;
  return Math.min(NOTES_FONT_MAX, Math.max(NOTES_FONT_MIN, Math.round(n)));
}

export function parseNotesTocWidth(raw: string | null | undefined): number {
  if (raw == null || raw === '') return NOTES_TOC_WIDTH_DEFAULT;
  const n = Number(raw);
  if (!Number.isFinite(n)) return NOTES_TOC_WIDTH_DEFAULT;
  return Math.min(NOTES_TOC_WIDTH_MAX, Math.max(NOTES_TOC_WIDTH_MIN, Math.round(n)));
}

export function parseSyncScroll(raw: string | null | undefined): boolean {
  if (raw === '0') return false;
  return true;
}

export function parseNotesSort(raw: string | null | undefined): NotesSort {
  if (raw === 'created' || raw === 'title' || raw === 'updated') return raw;
  return 'updated';
}

export function parseNotesFilter(raw: string | null | undefined): NotesFilter {
  if (raw === 'pinned' || raw === 'untitled' || raw === 'unlinked' || raw === 'today') return raw;
  return 'all';
}

export function parseNotesPanel(raw: string | null | undefined): NotesPanel {
  return raw === 'trash' ? 'trash' : 'none';
}

export function parseNotesDensity(raw: string | null | undefined): NotesDensity {
  return raw === 'compact' ? 'compact' : 'comfortable';
}

export function parseNotesQuery(raw: string | null | undefined): string {
  return String(raw ?? '').slice(0, QUERY_MAX);
}

export function parseNotesSourceId(raw: string | null | undefined): string {
  const id = String(raw ?? '').trim();
  if (!id || id.includes('/') || id.includes('\\') || id.includes('..')) return '';
  return id.slice(0, SOURCE_MAX);
}

/** 预览里拖选的词/句:压空白、截断。空串表示没有有效选区。 */
export function parseNotesQuote(raw: string | null | undefined): string {
  return String(raw ?? '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, NOTES_QUOTE_MAX);
}

let lastExplainQuote = '';

export function rememberNotesQuote(quote: string): void {
  lastExplainQuote = parseNotesQuote(quote);
}

export function lastNotesExplainQuote(): string {
  return lastExplainQuote;
}

/** 讲解请求的用户可见正文。agentName 由调用方传入显示名,本文件不绑具体人格。 */
export function buildNoteExplainMessage(opts: {
  quote: string;
  agentName: string;
  title?: string;
}): string {
  const quote = parseNotesQuote(opts.quote);
  const who = (opts.agentName || '').trim() || '助手';
  const title = (opts.title || '').trim().slice(0, 80);
  const where = title ? `《${title}》` : '这篇笔记';
  return (
    `${who}，请快速解读我在笔记${where}标出的内容：\n\n` +
    `「${quote}」\n\n` +
    `一两句话说明它是什么、在这篇里为什么出现。不要展开成课，不要重写整篇。`
  );
}

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

/** 按滚动比例把 from 同步到 to;可滚动距离为 0 时跳过。 */
export function syncScrollRatio(from: HTMLElement, to: HTMLElement): void {
  const fromMax = from.scrollHeight - from.clientHeight;
  const toMax = to.scrollHeight - to.clientHeight;
  if (fromMax <= 0 || toMax <= 0) return;
  to.scrollTop = (from.scrollTop / fromMax) * toMax;
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

/**
 * 行前缀切换:已是该前缀则去掉,否则换掉旧的标题/引用/列表前缀再套上新前缀。
 * `- ` 不误吞任务列表 `- [ ] `。
 */
export function applyLinePrefix(text: string, prefix: string): string {
  const isTask = /^[-*]\s\[[ x]\]\s/.test(text);
  if (text.startsWith(prefix) && !(prefix === '- ' && isTask)) {
    return text.slice(prefix.length);
  }
  const stripped = text.replace(/^(#{1,6}\s|>\s?|[-*]\s(?:\[[ x]\]\s)?|\d+\.\s)/, '');
  return prefix + stripped;
}

export interface NotesListingOpts<T = NoteListItem> {
  query?: string;
  filter?: NotesFilter;
  sort?: NotesSort;
  sourceId?: string;
  extraText?: (n: T) => string;
}

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

export interface NoteTocItem {
  level: number;
  text: string;
  line: number;
}

/** 提取 ATX 标题大纲,语义对齐后端 extract_toc:跳过围栏,行号 1 基。 */
export function extractNoteToc(content: string): NoteTocItem[] {
  const toc: NoteTocItem[] = [];
  let inFence = false;
  let fenceMarker = '';
  const lines = content.replace(/\r\n/g, '\n').split('\n');
  for (let i = 0; i < lines.length; i += 1) {
    const stripped = lines[i].replace(/^\s+/, '');
    const marker = stripped.slice(0, 3);
    if (marker === '```' || marker === '~~~') {
      if (!inFence) {
        inFence = true;
        fenceMarker = marker;
      } else if (marker === fenceMarker) {
        inFence = false;
      }
      continue;
    }
    if (inFence || !stripped.startsWith('#')) continue;
    const m = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(stripped);
    if (m) toc.push({ level: m[1].length, text: m[2].trim(), line: i + 1 });
  }
  return toc;
}

/** 目录展示与 slug 用可见标题,去掉底纹标记,对齐预览 nodeText。 */
export function tocHeadingLabel(text: string): string {
  const stripped = text.replace(new RegExp(`==(${NOTE_HL_KIND}):`, 'gi'), '').replace(/==/g, '').trim();
  return stripped || text;
}
