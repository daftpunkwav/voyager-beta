/** 笔记界面桥:启动拉取 + settings.changed / notes.ui.changed → store;可导航。
 *  挂在 AppShell,agent 在任意页调 set_notes_view 都能改笔记界面或打开一篇。 */

import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { subscribe } from '@/bridge/stream';
import { routes } from '@/utils/routes';
import { useFloatingStore } from '@/widgets/FloatingChat';
import { applyNotesSettingKey, applyNotesViewSnapshot, explainNotesQuote, fetchNotesView } from './notesView';

const NOTE_EVENTS = [
  'note.created',
  'note.edited',
  'note.deleted',
  'note.restored',
  'note.purged',
] as const;

export function useNotesUiBridge() {
  const navigate = useNavigate();
  const qc = useQueryClient();

  useEffect(() => {
    let alive = true;
    void fetchNotesView()
      .then((view) => {
        if (alive) applyNotesViewSnapshot(view);
      })
      .catch(() => {
        /* 后端未起:沿用 localStorage 种子,不打断壳 */
      });

    const offUi = subscribe(['notes.ui.changed', 'settings.changed'], (event) => {
      if (event.type === 'settings.changed') {
        const key = event.payload.key;
        if (typeof key === 'string' && key.startsWith('notes.ui.')) {
          applyNotesSettingKey(key, event.payload.value);
        }
        return;
      }
      applyNotesViewSnapshot(event.payload);
      const quote = typeof event.payload.quote === 'string' ? event.payload.quote : '';
      if (quote.trim()) {
        explainNotesQuote(quote);
      } else if (event.payload.assist === true) {
        useFloatingStore.getState().setOpen(true);
      }
      const action = event.payload.action;
      const noteId = event.payload.note_id;
      if (action === 'index') {
        navigate(routes.notes);
        return;
      }
      if (
        action === 'open' &&
        typeof noteId === 'string' &&
        noteId &&
        noteId.length <= 200 &&
        !noteId.includes('/') &&
        !noteId.includes('\\')
      ) {
        navigate(noteId === 'new' ? routes.note('new') : routes.note(noteId));
      }
    });

    const offNotes = subscribe([...NOTE_EVENTS], (event) => {
      void qc.invalidateQueries({ queryKey: ['notes'] });
      if (event.type === 'note.edited' || event.type === 'note.created') {
        const nid = event.payload.note_id;
        if (typeof nid === 'string' && nid) {
          void qc.invalidateQueries({ queryKey: ['note', nid] });
        }
      }
    });

    return () => {
      alive = false;
      offUi();
      offNotes();
    };
  }, [navigate, qc]);
}
