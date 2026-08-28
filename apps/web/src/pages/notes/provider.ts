/** 笔记页感知:只报视图/字号/当前篇标题,不带正文。 */

import type { PageProbe } from '@/bridge/pageContext';
import { lastNotesExplainQuote } from '@/pages/notes/noteUtils';
import { useNoteStore } from '@/stores/noteStore';
import { useNotesUiStore } from '@/stores/notesUiStore';

export const notesProvider: PageProbe = {
  page: 'notes',
  report() {
    const { editingNoteId, editorTitle } = useNoteStore.getState();
    const { mode, layout, fontSize, listState, sort, filter, query, panel } = useNotesUiStore.getState();
    const title = (editorTitle || '').trim().slice(0, 40);
    const quoted = lastNotesExplainQuote().trim().slice(0, 20);
    if (editingNoteId && editingNoteId !== 'new') {
      return {
        summary: `笔记工作区 · ${mode} · 字号 ${fontSize}${title ? ` · ${title}` : ''}${quoted ? ` · 讲解「${quoted}」` : ''}${panel === 'trash' ? ' · 回收站' : ''}`,
        selected: editingNoteId,
        counts: { font_size: fontSize },
      };
    }
    const q = query.trim().slice(0, 20);
    return {
      summary: `笔记首页 · ${layout} · ${listState === 'archived' ? '归档' : '当前'} · ${sort} · ${filter}${q ? ` · 「${q}」` : ''}${panel === 'trash' ? ' · 回收站' : ''}`,
      selected: editingNoteId === 'new' ? 'new' : '',
    };
  },
};
