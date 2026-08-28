/** 笔记页感知:只报视图/字号/当前篇标题,不带正文。 */

import type { PageProbe } from '@/bridge/pageContext';
import { useNoteStore } from '@/stores/noteStore';
import { useNotesUiStore } from '@/stores/notesUiStore';

export const notesProvider: PageProbe = {
  page: 'notes',
  report() {
    const { editingNoteId, editorTitle } = useNoteStore.getState();
    const { mode, layout, fontSize, listState } = useNotesUiStore.getState();
    const title = (editorTitle || '').trim().slice(0, 40);
    if (editingNoteId && editingNoteId !== 'new') {
      return {
        summary: `笔记工作区 · ${mode} · 字号 ${fontSize}${title ? ` · ${title}` : ''}`,
        selected: editingNoteId,
        counts: { font_size: fontSize },
      };
    }
    return {
      summary: `笔记首页 · ${layout} · ${listState === 'archived' ? '归档' : '在用'}`,
      selected: editingNoteId === 'new' ? 'new' : '',
    };
  },
};
