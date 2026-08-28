/** 笔记页界面状态。与 noteStore(正文)分离;与全站 appearance.font_scale 分离。 */

import { create } from 'zustand';
import { readKey, writeKey } from '@/brand';
import {
  NOTES_DENSITY_KEY,
  NOTES_FILTER_KEY,
  NOTES_FONT_KEY,
  NOTES_LAYOUT_KEY,
  NOTES_LIST_KEY,
  NOTES_MODE_KEY,
  NOTES_PANEL_KEY,
  NOTES_QUERY_KEY,
  NOTES_SORT_KEY,
  NOTES_SOURCE_KEY,
  NOTES_SPLIT_KEY,
  NOTES_SYNC_KEY,
  parseNotesDensity,
  parseNotesFilter,
  parseNotesFontSize,
  parseNotesLayout,
  parseNotesListState,
  parseNotesMode,
  parseNotesPanel,
  parseNotesQuery,
  parseNotesSort,
  parseNotesSourceId,
  parseSplitRatio,
  parseSyncScroll,
  type NotesDensity,
  type NotesFilter,
  type NotesLayout,
  type NotesListState,
  type NotesMode,
  type NotesPanel,
  type NotesSort,
} from '@/pages/notes/noteUtils';

export interface NotesUiState {
  fontSize: number;
  mode: NotesMode;
  layout: NotesLayout;
  listState: NotesListState;
  sort: NotesSort;
  filter: NotesFilter;
  query: string;
  sourceId: string;
  panel: NotesPanel;
  density: NotesDensity;
  splitRatio: number;
  syncScroll: boolean;
  apply: (patch: Partial<Omit<NotesUiState, 'apply' | 'setSplitRatio'>>) => void;
  setSplitRatio: (ratio: number) => void;
}

function seed(): Omit<NotesUiState, 'apply' | 'setSplitRatio'> {
  return {
    fontSize: parseNotesFontSize(readKey(NOTES_FONT_KEY, NOTES_FONT_KEY)),
    mode: parseNotesMode(readKey(NOTES_MODE_KEY, NOTES_MODE_KEY)),
    layout: parseNotesLayout(readKey(NOTES_LAYOUT_KEY, NOTES_LAYOUT_KEY)),
    listState: parseNotesListState(readKey(NOTES_LIST_KEY, NOTES_LIST_KEY)),
    sort: parseNotesSort(readKey(NOTES_SORT_KEY, NOTES_SORT_KEY)),
    filter: parseNotesFilter(readKey(NOTES_FILTER_KEY, NOTES_FILTER_KEY)),
    query: parseNotesQuery(readKey(NOTES_QUERY_KEY, NOTES_QUERY_KEY)),
    sourceId: parseNotesSourceId(readKey(NOTES_SOURCE_KEY, NOTES_SOURCE_KEY)),
    panel: parseNotesPanel(readKey(NOTES_PANEL_KEY, NOTES_PANEL_KEY)),
    density: parseNotesDensity(readKey(NOTES_DENSITY_KEY, NOTES_DENSITY_KEY)),
    splitRatio: parseSplitRatio(readKey(NOTES_SPLIT_KEY, NOTES_SPLIT_KEY)),
    syncScroll: parseSyncScroll(readKey(NOTES_SYNC_KEY, NOTES_SYNC_KEY)),
  };
}

export const useNotesUiStore = create<NotesUiState>((set) => ({
  ...seed(),
  apply: (patch) => set(patch),
  setSplitRatio: (splitRatio) => {
    set({ splitRatio });
    writeKey(NOTES_SPLIT_KEY, String(splitRatio));
  },
}));
