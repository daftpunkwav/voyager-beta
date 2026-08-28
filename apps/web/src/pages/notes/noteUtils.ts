/** 笔记页纯函数:偏好 / 源 ID / 行前缀 / 时间标签。不依赖 React。 */

import { formatRelativeTime } from '@/utils/date';

export const NOTES_MODE_KEY = 'notes-mode';
export const NOTES_LAYOUT_KEY = 'notes-layout';
export const NOTES_SPLIT_KEY = 'notes-split';
export const NOTES_FONT_KEY = 'notes-font';
export const NOTES_SYNC_KEY = 'notes-sync-scroll';
export const NOTES_LIST_KEY = 'notes-list-state';

export const NOTES_FONT_MIN = 13;
export const NOTES_FONT_MAX = 20;
export const NOTES_FONT_DEFAULT = 15;

export type NotesMode = 'edit' | 'preview' | 'split';
export type NotesLayout = 'list' | 'card';
export type NotesListState = 'active' | 'archived';

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

export function parseSyncScroll(raw: string | null | undefined): boolean {
  if (raw === '0') return false;
  return true;
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

/** 统一成毫秒。后端 updated_ts 多为秒;updated_at 为 ISO。 */
export function noteUpdatedMs(n: { updated_at?: string; updated_ts?: number }): number {
  if (typeof n.updated_ts === 'number' && n.updated_ts > 0) {
    return n.updated_ts < 1e12 ? n.updated_ts * 1000 : n.updated_ts;
  }
  return Date.parse(String(n.updated_at ?? '')) || 0;
}

export function noteUpdatedLabel(n: { updated_at?: string; updated_ts?: number }): string {
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

export type NotesSort = 'updated' | 'title';

/** 置顶始终在前;其余按最近更新或标题。 */
export function sortNotes<T extends {
  title?: string;
  pinned?: boolean;
  updated_ts?: number;
  updated_at?: string;
}>(notes: T[], sort: NotesSort): T[] {
  return [...notes].sort((a, b) => {
    const pin = Number(Boolean(b.pinned)) - Number(Boolean(a.pinned));
    if (pin !== 0) return pin;
    if (sort === 'title') {
      return (a.title || '').localeCompare(b.title || '', 'zh');
    }
    return noteUpdatedMs(b) - noteUpdatedMs(a);
  });
}
