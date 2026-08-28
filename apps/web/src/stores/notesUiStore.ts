/** 笔记页界面状态(字号/视图/布局)。与 noteStore(正文)分离;与全站 appearance.font_scale 分离。 */

import { create } from 'zustand';
import { readKey, writeKey } from '@/brand';
import {
  NOTES_FONT_KEY,
  NOTES_LAYOUT_KEY,
  NOTES_LIST_KEY,
  NOTES_MODE_KEY,
  NOTES_SPLIT_KEY,
  NOTES_SYNC_KEY,
  parseNotesFontSize,
  parseNotesLayout,
  parseNotesListState,
  parseNotesMode,
  parseSplitRatio,
  parseSyncScroll,
  type NotesLayout,
  type NotesListState,
  type NotesMode,
} from '@/pages/notes/noteUtils';

export interface NotesUiState {
  fontSize: number;
  mode: NotesMode;
  layout: NotesLayout;
  listState: NotesListState;
  splitRatio: number;
  syncScroll: boolean;
  apply: (patch: Partial<Omit<NotesUiState, 'apply' | 'setSplitRatio'>>) => void;
  setSplitRatio: (ratio: number) => void;
}

function seed(): Pick<
  NotesUiState,
  'fontSize' | 'mode' | 'layout' | 'listState' | 'splitRatio' | 'syncScroll'
> {
  return {
    fontSize: parseNotesFontSize(readKey(NOTES_FONT_KEY, NOTES_FONT_KEY)),
    mode: parseNotesMode(readKey(NOTES_MODE_KEY, NOTES_MODE_KEY)),
    layout: parseNotesLayout(readKey(NOTES_LAYOUT_KEY, NOTES_LAYOUT_KEY)),
    listState: parseNotesListState(readKey(NOTES_LIST_KEY, NOTES_LIST_KEY)),
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
