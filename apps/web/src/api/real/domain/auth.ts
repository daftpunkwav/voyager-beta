/**
 * 本机身份 / GitHub —— me / GitHub 账号 / Stars
 */
import type { ApiResponse, GitHubAccount, StarsListResult, User } from '@/api/types';
import type { HttpCtx } from './http-ctx';

export class AuthApi {
  constructor(private readonly ctx: HttpCtx) {}

  async me(): Promise<ApiResponse<User>> {
    return this.ctx.apiRequest<User>('/user/me');
  }

  async listGithubAccounts(): Promise<ApiResponse<GitHubAccount[]>> {
    return this.ctx.apiRequest<GitHubAccount[]>('/github/accounts');
  }

  async bindGithub(params: { username: string; pat: string }): Promise<ApiResponse<GitHubAccount>> {
    return this.ctx.apiRequest<GitHubAccount>('/github/bindaccount', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  }

  async unbindGithub(id: string): Promise<ApiResponse<{ success: boolean }>> {
    return this.ctx.apiRequest(`/github/accounts/${id}`, { method: 'DELETE' });
  }

  async listStars(params?: { username?: string; refresh?: boolean }): Promise<ApiResponse<StarsListResult>> {
    return this.ctx.apiRequest<StarsListResult>('/github/stars', {}, {
      username: params?.username,
      refresh: params?.refresh ? 'true' : undefined,
    });
  }
}
