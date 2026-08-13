/**
 * Notes Óò ¡ª ±Ê¼Ç CRUD
 */
import type { ApiResponse, Note } from '@/api/types';
import type { HttpCtx } from './http-ctx';

export class NotesApi {
  constructor(private readonly ctx: HttpCtx) {}

  async listNotes(projectId: string): Promise<ApiResponse<Note[]>> {
    return this.ctx.apiRequest<Note[]>(`/notes/projects/${projectId}/notes`);
  }

  async listAllNotes(): Promise<ApiResponse<Note[]>> {
    return this.ctx.apiRequest<Note[]>('/notes/');
  }

  async getNote(id: string): Promise<ApiResponse<Note>> {
    return this.ctx.apiRequest<Note>(`/notes/${id}`);
  }

  async createNote(projectId: string, data: { title: string; content: string }): Promise<ApiResponse<Note>> {
    return this.ctx.apiRequest<Note>(`/notes/projects/${projectId}/notes`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateNote(id: string, data: Partial<Note>): Promise<ApiResponse<Note>> {
    return this.ctx.apiRequest<Note>(`/notes/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteNote(id: string): Promise<ApiResponse<{ success: boolean }>> {
    return this.ctx.apiRequest(`/notes/${id}`, { method: 'DELETE' });
  }
}
