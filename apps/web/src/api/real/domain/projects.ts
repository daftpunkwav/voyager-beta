/**
 * Projects 域 — 项目 CRUD / 进度 / 统计 / 导入 / 分类 / 标签
 * 对应 IApiClient 的 projects/categories/tags 子集,共 18 个方法
 */
import type {
  ApiResponse,
  Category,
  CreateProjectInput,
  ImportResult,
  PaginatedList,
  Project,
  ProjectListParams,
  ProjectReadme,
  ProjectStats,
  Tag,
} from '@/api/types';
import type { HttpCtx } from './http-ctx';

export class ProjectsApi {
  constructor(private readonly ctx: HttpCtx) {}

  async importProjects(repos: Array<{ owner: string; repo: string; url: string }>): Promise<ApiResponse<ImportResult>> {
    return this.ctx.apiRequest<ImportResult>('/projects/import', {
      method: 'POST',
      body: JSON.stringify({ repos }),
    });
  }

  async listProjects(params?: ProjectListParams): Promise<ApiResponse<PaginatedList<Project>>> {
    return this.ctx.apiRequest<PaginatedList<Project>>('/projects/', {}, {
      search: params?.search,
      language: params?.language,
      category_id: params?.category_id,
      tag_id: params?.tag_id,
      sort_by: params?.sort_by,
      progress: params?.progress,
      page: params?.page,
      page_size: params?.page_size,
    });
  }

  async getProject(id: string): Promise<ApiResponse<Project>> {
    return this.ctx.apiRequest<Project>(`/projects/${id}`);
  }

  async getProjectReadme(id: string): Promise<ApiResponse<ProjectReadme>> {
    return this.ctx.apiRequest<ProjectReadme>(`/projects/${id}/readme`);
  }

  async createProject(data: CreateProjectInput): Promise<ApiResponse<Project>> {
    return this.ctx.apiRequest<Project>('/projects/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateProject(id: string, data: Partial<Project>): Promise<ApiResponse<Project>> {
    return this.ctx.apiRequest<Project>(`/projects/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteProject(id: string): Promise<ApiResponse<{ success: boolean }>> {
    return this.ctx.apiRequest(`/projects/${id}`, { method: 'DELETE' });
  }

  async updateProgress(
    id: string,
    progress: Project['progress']
  ): Promise<ApiResponse<{ id: string; progress: string }>> {
    return this.ctx.apiRequest(`/projects/${id}/progress`, { method: 'PUT' }, { progress });
  }

  async getProjectStats(): Promise<ApiResponse<ProjectStats>> {
    return this.ctx.apiRequest<ProjectStats>('/projects/stats');
  }

  async exportProjects(): Promise<ApiResponse<Project[]>> {
    const all: Project[] = [];
    let page = 1;
    const page_size = 100;
    while (true) {
      const res = await this.listProjects({ page, page_size });
      all.push(...res.data.items);
      if (all.length >= res.data.total) break;
      page += 1;
    }
    return { data: all, meta: { ts: Date.now(), total: all.length } };
  }

  async listCategories(): Promise<ApiResponse<Category[]>> {
    return this.ctx.apiRequest<Category[]>('/categories/');
  }

  async createCategory(data: { name: string }): Promise<ApiResponse<Category>> {
    return this.ctx.apiRequest<Category>('/categories/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateCategory(id: string, data: { name: string }): Promise<ApiResponse<Category>> {
    return this.ctx.apiRequest<Category>(`/categories/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteCategory(id: string): Promise<ApiResponse<{ success: boolean }>> {
    return this.ctx.apiRequest(`/categories/${id}`, { method: 'DELETE' });
  }

  async listTags(): Promise<ApiResponse<Tag[]>> {
    return this.ctx.apiRequest<Tag[]>('/tags/');
  }

  async createTag(data: { name: string }): Promise<ApiResponse<Tag>> {
    return this.ctx.apiRequest<Tag>('/tags/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async deleteTag(id: string): Promise<ApiResponse<{ success: boolean }>> {
    return this.ctx.apiRequest(`/tags/${id}`, { method: 'DELETE' });
  }

  async setProjectTags(
    projectId: string,
    tagIds: string[]
  ): Promise<ApiResponse<{ project_id: string; tag_ids: string[] }>> {
    const res = await this.ctx.apiRequest<{ project_id: string; tag_ids: string[] }>(
      `/tags/projects/${projectId}`,
      {
        method: 'PUT',
        body: JSON.stringify({ tag_ids: tagIds }),
      }
    );
    return {
      data: {
        project_id: String(res.data.project_id),
        tag_ids: res.data.tag_ids.map(String),
      },
      meta: res.meta,
    };
  }
}
