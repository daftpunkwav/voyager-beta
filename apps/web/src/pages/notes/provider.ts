/** 笔记页感知:只报列表条数/视图/当前篇标题/讲解选区指针,不带正文。 */

import type { PageProbe } from '@/bridge/pageContext';
import { lastNotesExplainQuote } from './noteQuote';
import { useNoteStore } from '@/stores/noteStore';
import { useNotesUiStore } from './notesUiStore';

/** 列表条数的 module cache(学 noteQuote.ts 先例):列表数据在 react-query 里,
 * provider 读不到;由 NotesPage 在数据到达时写入, null=列表从未到达(不谎报 0 条)。 */
let listCount: number | null = null;

export function rememberNotesListCount(count: number | null): void {
  listCount = count;
}

export function lastNotesListCount(): number | null {
  return listCount;
}

/** 标题截断(§9.20:摘要单行可控)。 */
function clipTitle(title: string, max = 40): string {
  return title.trim().slice(0, max);
}

export const notesProvider: PageProbe = {
  page: 'notes',
  report() {
    const { editingNoteId, editorTitle } = useNoteStore.getState();
    const { mode, layout, fontSize, listState, sort, filter, query, panel } = useNotesUiStore.getState();
    const title = clipTitle(editorTitle || '');
    const quoted = lastNotesExplainQuote().trim().slice(0, 20);
    // 列表条数:cache 为 null 时不说条数(列表从未到达);0 条是真实状态照报
    const n = listCount;
    const countPart = n === null ? '' : ` · ${n} 条笔记`;
    const counts = n === null ? undefined : { notes: n };
    if (editingNoteId && editingNoteId !== 'new') {
      return {
        summary: `笔记工作区${countPart} · ${mode} · 字号 ${fontSize}${title ? ` · 《${title}》` : ''}${quoted ? ` · 讲解「${quoted}」` : ''}${panel === 'trash' ? ' · 回收站' : ''}`,
        selected: editingNoteId,
        counts,
      };
    }
    const q = query.trim().slice(0, 20);
    return {
      summary: `笔记首页${countPart} · ${layout} · ${listState === 'archived' ? '归档' : '当前'} · ${sort} · ${filter}${q ? ` · 「${q}」` : ''}${panel === 'trash' ? ' · 回收站' : ''}`,
      selected: editingNoteId === 'new' ? 'new' : '',
      counts,
    };
  },
};
