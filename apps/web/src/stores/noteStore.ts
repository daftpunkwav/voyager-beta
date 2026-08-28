import { create } from 'zustand';

/** 笔记正文编辑态。界面偏好(字号/视图)在 notesUiStore,不要混进来。 */

interface NoteState {
  editingNoteId: string | null;
  editorContent: string;
  editorTitle: string;
  searchQuery: string;
  selectedNoteId: string | null;
  startEditing: (noteId: string, title: string, content: string) => void;
  stopEditing: () => void;
  setEditorContent: (content: string) => void;
  setEditorTitle: (title: string) => void;
  setSearchQuery: (query: string) => void;
  setSelectedNoteId: (id: string | null) => void;
}

export const useNoteStore = create<NoteState>((set) => ({
  editingNoteId: null,
  editorContent: '',
  editorTitle: '',
  searchQuery: '',
  selectedNoteId: null,

  startEditing: (noteId, title, content) =>
    set({
      editingNoteId: noteId,
      editorTitle: title,
      editorContent: content,
      selectedNoteId: noteId,
    }),

  stopEditing: () =>
    set({
      editingNoteId: null,
      editorContent: '',
      editorTitle: '',
      selectedNoteId: null,
    }),

  setEditorContent: (content) => set({ editorContent: content }),
  setEditorTitle: (title) => set({ editorTitle: title }),
  setSearchQuery: (query) => set({ searchQuery: query }),
  setSelectedNoteId: (id) => set({ selectedNoteId: id }),
}));
