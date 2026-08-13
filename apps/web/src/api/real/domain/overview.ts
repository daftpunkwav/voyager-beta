/**
 * Overview Óò ¡ª Ê×Ò³¸ÅÀÀÊý¾Ý
 *   listTrending / streamTrendingScoutIntro / listActivities / listRecommendedProjects / listOverviewRecentNotes
 */
import type {
  ActivityItem,
  ApiResponse,
  OverviewRecentNote,
  RecommendedProject,
  SSEEvent,
  TrendingPeriod,
  TrendingRepo,
  TrendingScoutIntroParams,
} from '@/api/types';
import { parseSSEStream } from '@/utils/sse-parser';
import type { HttpCtx } from './http-ctx';

export class OverviewApi {
  constructor(private readonly ctx: HttpCtx) {}

  async listTrending(params?: { period?: TrendingPeriod; language?: string }): Promise<ApiResponse<TrendingRepo[]>> {
    return this.ctx.apiRequest<TrendingRepo[]>('/overview/trending', {}, {
      period: params?.period,
      language: params?.language,
    });
  }

  /** Scout ¸ÅÊö trending ²Ö¿â½éÉÜ(SSE;ÔÝÎ´¶Ô½Ó LLM) */
  async *streamTrendingScoutIntro(
    params: TrendingScoutIntroParams,
    signal?: AbortSignal
  ): AsyncGenerator<SSEEvent> {
    const res = await this.ctx.apiSSE(
      '/agent/trending-scout',
      params as unknown as Record<string, unknown>,
      signal
    );
    if (!res.body) return;
    const reader = res.body.getReader();
    yield* parseSSEStream(reader, signal);
  }

  async listActivities(): Promise<ApiResponse<ActivityItem[]>> {
    return this.ctx.apiRequest<ActivityItem[]>('/overview/activities');
  }

  async listRecommendedProjects(params?: { limit?: number }): Promise<ApiResponse<RecommendedProject[]>> {
    return this.ctx.apiRequest<RecommendedProject[]>('/overview/recommended', {}, {
      limit: params?.limit,
    });
  }

  async listOverviewRecentNotes(params?: { limit?: number }): Promise<ApiResponse<OverviewRecentNote[]>> {
    return this.ctx.apiRequest<OverviewRecentNote[]>('/overview/recent-notes', {}, {
      limit: params?.limit,
    });
  }
}
