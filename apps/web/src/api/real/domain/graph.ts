/**
 * Graph �� �� L0 ��Ŀͼ�� + L1 ����ͼ�� + ����
 */
import type { ApiResponse, GraphData, StarRepo } from '@/api/types';
import type { GraphIndexStatus } from '@/components/code-graph/types';
import type { HttpCtx } from './http-ctx';

export class GraphApi {
  constructor(private readonly ctx: HttpCtx) {}

  async getGraph(params?: {
    min_similarity?: number;
    max_edges?: number;
  }): Promise<ApiResponse<GraphData>> {
    return this.ctx.apiRequest<GraphData>(
      '/graph/',
      {},
      {
        min_similarity: params?.min_similarity,
        max_edges: params?.max_edges,
      },
    );
  }

  async getCrossEdges(): Promise<
    ApiResponse<{ edges: Array<Record<string, unknown>>; stats: { edge_count: number } }>
  > {
    return this.ctx.apiRequest('/graph/cross-edges');
  }

  async getRecommendEdges(): Promise<
    ApiResponse<{
      edges: Array<Record<string, unknown>>;
      stats: { edge_count: number };
      meta?: Record<string, unknown>;
    }>
  > {
    return this.ctx.apiRequest('/graph/recommend-edges');
  }

  async listCodeGraphIndexStatuses(): Promise<
    ApiResponse<{
      items: Array<Record<string, unknown>>;
      active: Array<Record<string, unknown>>;
      stats: { total: number; running: number; ready: number; failed: number };
    }>
  > {
    return this.ctx.apiRequest('/graph/index-statuses');
  }

  async cancelCodeGraphIndex(projectId: string): Promise<ApiResponse<GraphIndexStatus>> {
    return this.ctx.apiRequest(`/graph/projects/${projectId}/index/cancel`, {
      method: 'POST',
    });
  }

  async getCodeGraphStatus(projectId: string): Promise<ApiResponse<GraphIndexStatus>> {
    return this.ctx.apiRequest(`/graph/projects/${projectId}/status`);
  }

  async triggerCodeGraphIndex(
    projectId: string,
    body?: { mode?: 'fast' | 'moderate' | 'full' },
  ): Promise<ApiResponse<GraphIndexStatus>> {
    return this.ctx.apiRequest(`/graph/projects/${projectId}/index`, {
      method: 'POST',
      body: JSON.stringify(body || { mode: 'fast' }),
    });
  }

  async refreshCodeGraphIndex(
    projectId: string,
    body?: { mode?: 'fast' | 'moderate' | 'full' },
  ): Promise<ApiResponse<GraphIndexStatus>> {
    return this.ctx.apiRequest(`/graph/projects/${projectId}/refresh`, {
      method: 'POST',
      body: JSON.stringify(body || { mode: 'fast' }),
    });
  }

  async deleteCodeGraphIndex(projectId: string): Promise<ApiResponse<GraphIndexStatus>> {
    return this.ctx.apiRequest(`/graph/projects/${projectId}/index`, {
      method: 'DELETE',
    });
  }

  async getCodeGraph(
    projectId: string,
    params?: { max_nodes?: number },
  ): Promise<ApiResponse<Record<string, unknown>>> {
    return this.ctx.apiRequest(`/graph/projects/${projectId}`, {}, {
      max_nodes: params?.max_nodes,
    });
  }

  async getCodeArchitecture(projectId: string): Promise<ApiResponse<Record<string, unknown>>> {
    return this.ctx.apiRequest(`/graph/projects/${projectId}/architecture`);
  }

  async traceCodeGraph(
    projectId: string,
    body: { symbol: string; direction?: string; depth?: number },
  ): Promise<ApiResponse<Record<string, unknown>>> {
    return this.ctx.apiRequest(`/graph/projects/${projectId}/trace`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async searchCodeGraph(
    projectId: string,
    body: { query: string; label?: string; limit?: number },
  ): Promise<ApiResponse<Record<string, unknown>>> {
    return this.ctx.apiRequest(`/graph/projects/${projectId}/search`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async batchIndexCodeGraph(
    projectIds: string[],
    mode: 'fast' | 'moderate' | 'full' = 'fast',
  ): Promise<ApiResponse<{ queued: string[]; failed: string[] }>> {
    return this.ctx.apiRequest('/graph/projects/index-batch', {
      method: 'POST',
      body: JSON.stringify({ project_ids: projectIds, mode }),
    });
  }

  async getLlmUsage(days = 30): Promise<ApiResponse<import('@/api/types').LlmUsageSummary>> {
    return this.ctx.apiRequest('/usage/llm', {}, { days });
  }

  async searchGithubRepos(query: string): Promise<ApiResponse<StarRepo[]>> {
    return this.ctx.apiRequest<StarRepo[]>('/github/search', {}, { q: query });
  }
}
