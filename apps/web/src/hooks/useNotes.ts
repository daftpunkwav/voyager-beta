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
