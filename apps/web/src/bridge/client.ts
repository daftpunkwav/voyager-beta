/** 统一能力调用通道:POST /api/<domain>/capabilities/<name>,统一解 {result}/{error} 信封。 */

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
      headers: {
        'Content-Type': 'application/json',
        'X-Trace-Id': crypto.randomUUID(),
      },
      body: JSON.stringify(args),
    });
  } catch {
    throw new ServiceError('NETWORK', '无法连接后端服务', '请确认后端已启动');
  }

  const body = await resp.json().catch(() => null);
  if (!resp.ok) {
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
