/** 笔记界面偏好:本地缓存 + 后端 get/set_notes_view(用户按钮与 agent 同权)。 */

import { writeKey } from '@/brand';
import { callCapability } from '@/bridge/client';
import { useNotesUiStore } from '@/stores/notesUiStore';
import {
  NOTES_FONT_KEY,
  NOTES_FONT_MAX,
  NOTES_FONT_MIN,
  NOTES_LAYOUT_KEY,
  NOTES_LIST_KEY,
  NOTES_MODE_KEY,
  NOTES_SYNC_KEY,
  parseNotesFontSize,
  parseNotesLayout,
  parseNotesListState,
  parseNotesMode,
  parseSyncScroll,
  type NotesLayout,
  type NotesListState,
  type NotesMode,
} from './noteUtils';

export interface NotesViewSnapshot {
  font_size: number;
  mode: NotesMode;
  layout: NotesLayout;
  sync_scroll: boolean;
  list_state: NotesListState;
  persisted?: boolean;
  action?: 'open' | 'index' | null;
  note_id?: string | null;
}

export interface NotesViewPatch {
  font_size?: number;
  font_delta?: number;
  mode?: NotesMode;
  layout?: NotesLayout;
  sync_scroll?: boolean;
  list_state?: NotesListState;
  note_id?: string;
  index?: boolean;
}

function cacheLocal(s: {
  fontSize: number;
  mode: NotesMode;
  layout: NotesLayout;
  listState: NotesListState;
  syncScroll: boolean;
}): void {
  writeKey(NOTES_FONT_KEY, String(s.fontSize));
  writeKey(NOTES_MODE_KEY, s.mode);
  writeKey(NOTES_LAYOUT_KEY, s.layout);
  writeKey(NOTES_LIST_KEY, s.listState);
  writeKey(NOTES_SYNC_KEY, s.syncScroll ? '1' : '0');
}

/** 把后端快照写进 store + localStorage 缓存(后端不可用时下次还能读到)。 */
export function applyNotesViewSnapshot(raw: Partial<NotesViewSnapshot> | Record<string, unknown>): void {
  const patch: {
    fontSize?: number;
    mode?: NotesMode;
    layout?: NotesLayout;
    listState?: NotesListState;
    syncScroll?: boolean;
  } = {};
  if (raw.font_size != null) patch.fontSize = parseNotesFontSize(String(raw.font_size));
  if (raw.mode != null) patch.mode = parseNotesMode(String(raw.mode));
  if (raw.layout != null) patch.layout = parseNotesLayout(String(raw.layout));
  if (raw.list_state != null) patch.listState = parseNotesListState(String(raw.list_state));
  if (raw.sync_scroll != null) {
    patch.syncScroll =
      typeof raw.sync_scroll === 'boolean'
        ? raw.sync_scroll
        : parseSyncScroll(String(raw.sync_scroll));
  }
  if (Object.keys(patch).length === 0) return;
  useNotesUiStore.getState().apply(patch);
  const s = useNotesUiStore.getState();
  cacheLocal(s);
}

export function applyNotesSettingKey(key: string, value: unknown): void {
  if (key === 'notes.ui.font_size') {
    applyNotesViewSnapshot({ font_size: Number(value) });
    return;
  }
  if (key === 'notes.ui.mode') {
    applyNotesViewSnapshot({ mode: String(value) as NotesMode });
    return;
  }
  if (key === 'notes.ui.layout') {
    applyNotesViewSnapshot({ layout: String(value) as NotesLayout });
    return;
  }
  if (key === 'notes.ui.list_state') {
    applyNotesViewSnapshot({ list_state: String(value) as NotesListState });
    return;
  }
  if (key === 'notes.ui.sync_scroll') {
    applyNotesViewSnapshot({ sync_scroll: value === true || value === 'true' || value === 1 });
  }
}

export async function fetchNotesView(): Promise<NotesViewSnapshot> {
  return callCapability<NotesViewSnapshot>('notes', 'get_notes_view');
}

export async function setNotesView(args: NotesViewPatch): Promise<NotesViewSnapshot> {
  return callCapability<NotesViewSnapshot>(
    'notes',
    'set_notes_view',
    { ...args } as Record<string, unknown>,
  );
}

/** 只把本次改动写回。乐观更新已在 store;事件/settings.changed 再对齐。 */
export function persistNotesView(args: NotesViewPatch): void {
  void setNotesView(args).catch(() => {
    /* 后端不可达:界面以本地缓存为准,不假装已同步 */
  });
}

export function commitNotesFont(size: number): void {
  const fontSize = parseNotesFontSize(String(size));
  useNotesUiStore.getState().apply({ fontSize });
  writeKey(NOTES_FONT_KEY, String(fontSize));
  persistNotesView({ font_size: fontSize });
}

export function commitNotesMode(mode: NotesMode): void {
  useNotesUiStore.getState().apply({ mode });
  writeKey(NOTES_MODE_KEY, mode);
  persistNotesView({ mode });
}

export function commitNotesLayout(layout: NotesLayout): void {
  useNotesUiStore.getState().apply({ layout });
  writeKey(NOTES_LAYOUT_KEY, layout);
  persistNotesView({ layout });
}

export function commitNotesListState(listState: NotesListState): void {
  useNotesUiStore.getState().apply({ listState });
  writeKey(NOTES_LIST_KEY, listState);
  persistNotesView({ list_state: listState });
}

export function commitNotesSyncScroll(syncScroll: boolean): void {
  useNotesUiStore.getState().apply({ syncScroll });
  writeKey(NOTES_SYNC_KEY, syncScroll ? '1' : '0');
  persistNotesView({ sync_scroll: syncScroll });
}

export function bumpNotesFont(delta: number): void {
  const cur = useNotesUiStore.getState().fontSize;
  const next = Math.min(NOTES_FONT_MAX, Math.max(NOTES_FONT_MIN, cur + delta));
  commitNotesFont(next);
}
