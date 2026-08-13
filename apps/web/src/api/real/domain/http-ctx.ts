/**
 * 子域共享的 HTTP 上下文 — 由 RealApiClient 注入 apiRequest / apiSSE
 */
import type { apiRequest, apiSSE } from '../http';

export interface HttpCtx {
  apiRequest: typeof apiRequest;
  apiSSE: typeof apiSSE;
}
