/** 笔记页 provider:对外暴露索引级摘要，不暴露 store 实现。 */

import type { PageProbe } from '@/bridge/pageContext';
import { useNotesStore } from './notesStore';

export const notesProvider: PageProbe = {
  page: 'notes',
  report() {
    const { summaries, current, loading } = useNotesStore.getState();
    if (loading && summaries.length === 0) return null;
    return {
      summary: current
        ? `${summaries.length} 篇笔记,当前打开《${current.title}》`
        : `${summaries.length} 篇笔记`,
      counts: { notes: summaries.length },
      selected: current?.title ?? '',
    };
  },
};
