/** HTTP 客户端 —— 真实后端请求（本地单机无认证） */
import type { ApiResponse } from 'types';

const API_PREFIX = '/api/v1';

/** 统一的 API 错误类；保留后端 detail.code */
export class ApiRequestError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number = 0) {
    super(message);
    this.name = 'ApiRequestError';
    this.code = code;
    this.status = status;
  }
}

function baseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL ?? '';
}

function buildUrl(path: string, params?: Record<string, string | number | undefined>): string {
  const url = new URL(`${baseUrl()}${API_PREFIX}${path}`, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== '') url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

/** 清除历史 localStorage 凭证（升级后遗留清理，一次性） */
export function clearLegacyTokenStorage(): void {
  try {
    localStorage.removeItem('rp_token');
    localStorage.removeItem('rp_refresh');
  } catch {
    /* 隐私模式等 */
  }
}

/** 从错误体提取 code + message（保留后端 detail.code） */
export function extractApiError(res: Response, body: unknown): ApiRequestError {
  if (typeof body === 'object' && body !== null) {
    const obj = body as Record<string, unknown>;
    const detail = obj.detail;
    if (typeof detail === 'object' && detail !== null) {
      const d = detail as { code?: unknown; message?: unknown };
      if (typeof d.code === 'string' && typeof d.message === 'string') {
        return new ApiRequestError(d.code, d.message, res.status);
      }
      if (typeof d.message === 'string') {
        return new ApiRequestError('API_ERROR', d.message, res.status);
      }
    }
    const err = obj.error;
    if (typeof err === 'object' && err !== null) {
      const e = err as { code?: unknown; message?: unknown };
      if (typeof e.code === 'string' && typeof e.message === 'string') {
        return new ApiRequestError(e.code, e.message, res.status);
      }
      if (typeof e.message === 'string') {
        return new ApiRequestError('API_ERROR', e.message, res.status);
      }
    }
    if (Array.isArray(detail) && detail.length) {
      const first = detail[0] as { msg?: string };
      return new ApiRequestError(
        'VALIDATION_ERROR',
        first?.msg ?? '参数校验失败',
        res.status,
      );
    }
    if (typeof detail === 'string') {
      return new ApiRequestError('API_ERROR', detail, res.status);
    }
  }
  return new ApiRequestError('API_ERROR', '请求失败', res.status);
}

async function parseJson<T>(res: Response): Promise<ApiResponse<T>> {
  const text = await res.text();
  let json: unknown = null;
  if (text) {
    try {
      json = JSON.parse(text) as unknown;
    } catch {
      const snippet = text.replace(/\s+/g, ' ').trim().slice(0, 240);
      throw new ApiRequestError(
        'API_ERROR',
        snippet || `请求失败（HTTP ${res.status}）`,
        res.status,
      );
    }
  }
  if (!res.ok) {
    throw extractApiError(res, json);
  }
  return json as ApiResponse<T>;
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  params?: Record<string, string | number | undefined>
): Promise<ApiResponse<T>> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const res = await fetch(buildUrl(path, params), {
    ...options,
    headers,
  });
  return parseJson<T>(res);
}

export async function apiSSE(
  path: string,
  body: unknown,
  signal?: AbortSignal
): Promise<Response> {
  const headers = new Headers({
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  });

  const res = await fetch(buildUrl(path), {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    let err = new ApiRequestError('API_ERROR', '请求失败', res.status);
    try {
      const json = await res.json();
      err = extractApiError(res, json);
    } catch {
      /* 非 JSON 错误体 */
    }
    throw err;
  }
  return res;
}
