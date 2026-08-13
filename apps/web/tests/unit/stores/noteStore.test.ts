import { beforeEach, describe, expect, it } from 'vitest';
import { useNoteStore } from '@/stores/noteStore';

describe('noteStore', () => {
  beforeEach(() => {
    useNoteStore.setState({
      editingNoteId: null,
      editorContent: '',
      editorTitle: '',
      previewMode: false,
      searchQuery: '',
      selectedNoteId: null,
    });
  });

  it('startEditing populates all editor fields', () => {
    useNoteStore.getState().startEditing('n_1', 'Hello', 'world');
    const s = useNoteStore.getState();
    expect(s.editingNoteId).toBe('n_1');
    expect(s.editorTitle).toBe('Hello');
    expect(s.editorContent).toBe('world');
    expect(s.selectedNoteId).toBe('n_1');
    expect(s.previewMode).toBe(false);
  });

  it('stopEditing clears fields but keeps selectedNoteId', () => {
    useNoteStore.getState().startEditing('n_1', 'Hello', 'world');
    useNoteStore.getState().stopEditing();
    const s = useNoteStore.getState();
    expect(s.editingNoteId).toBeNull();
    expect(s.editorTitle).toBe('');
    expect(s.editorContent).toBe('');
  });

  it('togglePreview flips boolean', () => {
    expect(useNoteStore.getState().previewMode).toBe(false);
    useNoteStore.getState().togglePreview();
    expect(useNoteStore.getState().previewMode).toBe(true);
    useNoteStore.getState().togglePreview();
    expect(useNoteStore.getState().previewMode).toBe(false);
  });
});