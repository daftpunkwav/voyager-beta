/** 统一能力调用通道:POST /api/<domain>/capabilities/<name>,统一解 {result}/{error} 信封。 */

import { BACKEND_UNREACHABLE } from '@/utils/errors';

export class ServiceError extends Error {
  constructor(
    public code: string,
    message: string,
    public hint = '',
    public traceId = '',
    public status = 0,
  ) {
    super(message);
    this.name = 'ServiceError';
  }
}

export async function callCapability<T = unknown>(
  domain: string,
  name: string,
  args: Record<string, unknown> = {},
): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`/api/${domain}/capabilities/${name}`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-Trace-Id': crypto.randomUUID(),
      },
      body: JSON.stringify(args),
    });
  } catch {
    throw new ServiceError('NETWORK', BACKEND_UNREACHABLE);
  }

  const body = await resp.json().catch(() => null);
  if (!resp.ok) {
    // 无 JSON 信封的失败响应(如 dev/preview 代理在后端未启动时返回的 500 空 body)
    // 对用户等价于"后端不可达",不展示含糊的"请求失败(500)"
    if (body === null) {
      throw new ServiceError('NETWORK', BACKEND_UNREACHABLE, '', '', resp.status);
    }
    const err = body?.error ?? {};
    throw new ServiceError(
      err.code ?? 'UNKNOWN',
      err.message ?? `请求失败(${resp.status})`,
      err.hint ?? '',
      err.trace_id ?? '',
      resp.status,
    );
  }
  return (body?.result ?? body) as T;
}

/** 浏览器文件上传(运输动作,非能力):落 workspace/imports/,返回服务器路径。
 *  业务校验(类型/大小上限)由后续领域能力(add_document / add_asset)强制。 */
export async function uploadFile(
  file: File,
): Promise<{ file_path: string; filename: string; size: number }> {
  const form = new FormData();
  form.append('file', file);
  let resp: Response;
  try {
    resp = await fetch('/api/uploads', {
      method: 'POST',
      credentials: 'include',
      body: form,
      headers: { 'X-Trace-Id': crypto.randomUUID() },
    });
  } catch {
    throw new ServiceError('NETWORK', BACKEND_UNREACHABLE);
  }
  const body = await resp.json().catch(() => null);
  if (!resp.ok) {
    const err = body?.error ?? {};
    throw new ServiceError(
      err.code ?? 'UNKNOWN',
      err.message ?? `上传失败(${resp.status})`,
      err.hint ?? '',
      err.trace_id ?? '',
      resp.status,
    );
  }
  return body as { file_path: string; filename: string; size: number };
}
