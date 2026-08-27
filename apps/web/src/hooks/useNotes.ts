import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getApi } from '@/api/client';
import { useNoteStore } from '@/stores/noteStore';
import { invalidateOverviewQueries } from '@/utils/invalidateOverview';

export function useAllNotes() {
  return useQuery({
    queryKey: ['notes', 'all'],
    queryFn: async () => {
      const api = getApi();
      const res = await api.listAllNotes();
      return res.data;
    },
  });
}

export function useProjectNotes(projectId: string | undefined) {
  return useQuery({
    queryKey: ['notes', projectId],
    queryFn: async () => {
      if (!projectId) throw new Error('missing projectId');
      const api = getApi();
      const res = await api.listNotes(projectId);
      return res.data;
    },
    enabled: Boolean(projectId),
  });
}

export function useNote(id: string | undefined) {
  return useQuery({
    queryKey: ['note', id],
    queryFn: async () => {
      if (!id) throw new Error('missing id');
      const api = getApi();
      const res = await api.getNote(id);
      return res.data;
    },
    enabled: Boolean(id),
  });
}

export function useCreateNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      projectId,
      title,
      content,
    }: {
      projectId: string;
      title: string;
      content: string;
    }) => {
      const api = getApi();
      const res = await api.createNote(projectId, { title, content });
      return res.data;
    },
    onSuccess: (note) => {
      void qc.invalidateQueries({ queryKey: ['notes'] });
      void invalidateOverviewQueries(qc);
      useNoteStore.getState().startEditing(note.id, note.title, note.content);
    },
  });
}

export function useUpdateNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      title,
      content,
    }: {
      id: string;
      title: string;
      content: string;
    }) => {
      const api = getApi();
      const res = await api.updateNote(id, { title, content });
      return res.data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notes'] });
      void invalidateOverviewQueries(qc);
    },
  });
}

export function useDeleteNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const api = getApi();
      await api.deleteNote(id);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notes'] });
      void invalidateOverviewQueries(qc);
      useNoteStore.getState().stopEditing();
    },
  });
}

// ---------- 功能面扩展(阶段 13):回收站/版本/标签/TOC/反链/导出/附件 ----------

/** 打开笔记前取全文(list_notes 只回摘要;直接装摘要会把正文截断)。 */
export async function fetchNoteFull(id: string): Promise<{ id: string; title: string; content: string }> {
  const res = await getApi().getNote(id);
  return res.data;
}

export function useNoteTags() {
  return useQuery({
    queryKey: ['noteTags'],
    queryFn: async () => (await getApi().listNoteTags()).data as { tag: string; count: number }[],
  });
}

export function useNoteToc(id: string | undefined) {
  return useQuery({
    queryKey: ['noteToc', id],
    queryFn: async () => {
      if (!id) throw new Error('missing id');
      return (await getApi().getNoteToc(id)).data as {
        toc: { level: number; text: string; line: number }[];
      };
    },
    enabled: Boolean(id),
    staleTime: 10_000,
  });
}

export function useBacklinks(id: string | undefined) {
  return useQuery({
    queryKey: ['noteBacklinks', id],
    queryFn: async () => {
      if (!id) throw new Error('missing id');
      return (await getApi().getBacklinks(id)).data as {
        backlinks: { id: string; title: string; excerpt: string; updated_ts: number }[];
      };
    },
    enabled: Boolean(id),
  });
}

export function useTrashNotes(enabled: boolean) {
  return useQuery({
    queryKey: ['notes', 'trash'],
    queryFn: async () => {
      const res = await getApi().searchNotes('', { state: 'trash' });
      return res.data as { id: string; title: string; updated_ts: number }[];
    },
    enabled,
  });
}

export function useRestoreNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await getApi().restoreNote(id);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notes'] });
    },
  });
}

export function usePurgeNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await getApi().purgeNote(id);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notes'] });
    },
  });
}

export function useEmptyTrash() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await getApi().emptyTrash();
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notes'] });
    },
  });
}

export function useNoteVersions(id: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ['noteVersions', id],
    queryFn: async () => {
      if (!id) throw new Error('missing id');
      return (await getApi().listVersions(id)).data as {
        versions: { version: number; ts: number; chars: number }[];
        current_chars: number;
      };
    },
    enabled: Boolean(id) && enabled,
  });
}

export function useRestoreVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { id: string; version: number }) => {
      const res = await getApi().restoreVersion(input.id, input.version);
      return res.data;
    },
    onSuccess: (note) => {
      void qc.invalidateQueries({ queryKey: ['notes'] });
      const n = note as { id: string; title: string; content: string };
      useNoteStore.getState().startEditing(n.id, n.title, n.content);
    },
  });
}

export function useExportNote() {
  return useMutation({
    mutationFn: async (id: string) => (await getApi().exportNote(id)).data as { path: string; chars: number },
  });
}

export function useRenameNoteTag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { old: string; new: string }) => {
      await getApi().renameNoteTag(input.old, input.new);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notes'] });
      void qc.invalidateQueries({ queryKey: ['noteTags'] });
    },
  });
}
