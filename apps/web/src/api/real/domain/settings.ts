/**
 * Settings �� �� �û����� + LLM API Key + �Բ�
 */
import type { ApiResponse, Settings } from '@/api/types';
import type { HttpCtx } from './http-ctx';

export class SettingsApi {
  constructor(private readonly ctx: HttpCtx) {}

  async getSettings(): Promise<ApiResponse<Settings>> {
    return this.ctx.apiRequest<Settings>('/settings/');
  }

  async updateSettings(data: Partial<Settings>): Promise<ApiResponse<Settings>> {
    return this.ctx.apiRequest<Settings>('/settings/', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async saveLlmApiKey(
    apiKey: string,
    providerId?: string,
  ): Promise<ApiResponse<{ masked: string; provider_id?: string | null }>> {
    return this.ctx.apiRequest<{ masked: string; provider_id?: string | null }>(
      '/settings/api-key',
      {
        method: 'POST',
        body: JSON.stringify({ api_key: apiKey, provider_id: providerId ?? null }),
      },
    );
  }

  async testLLM(params?: {
    model?: string;
    provider_id?: string;
  }): Promise<
    ApiResponse<{
      success: boolean;
      latency_ms: number;
      model: string;
      reply?: string;
      error?: string;
      litellm_model?: string;
      provider_id?: string | null;
    }>
  > {
    return this.ctx.apiRequest('/settings/test-llm', {
      method: 'POST',
      body: JSON.stringify({
        model: params?.model,
        provider_id: params?.provider_id,
      }),
    });
  }
}
