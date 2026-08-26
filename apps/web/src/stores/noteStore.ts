import { create } from 'zustand';

interface NoteState {
  editingNoteId: string | null;
  editorContent: string;
  editorTitle: string;
  previewMode: boolean;
  searchQuery: string;
  selectedNoteId: string | null;
  startEditing: (noteId: string, title: string, content: string) => void;
  stopEditing: () => void;
  setEditorContent: (content: string) => void;
  setEditorTitle: (title: string) => void;
  togglePreview: () => void;
  setSearchQuery: (query: string) => void;
  setSelectedNoteId: (id: string | null) => void;
}

export const useNoteStore = create<NoteState>((set) => ({
  editingNoteId: null,
  editorContent: '',
  editorTitle: '',
  previewMode: false,
  searchQuery: '',
  selectedNoteId: null,

  startEditing: (noteId, title, content) =>
    set({
      editingNoteId: noteId,
      editorTitle: title,
      editorContent: content,
      previewMode: false,
      selectedNoteId: noteId,
    }),

  stopEditing: () =>
    set({
      editingNoteId: null,
      editorContent: '',
      editorTitle: '',
      previewMode: false,
    }),

  setEditorContent: (content) => set({ editorContent: content }),
  setEditorTitle: (title) => set({ editorTitle: title }),
  togglePreview: () => set((state) => ({ previewMode: !state.previewMode })),
  setSearchQuery: (query) => set({ searchQuery: query }),
  setSelectedNoteId: (id) => set({ selectedNoteId: id }),
}));
