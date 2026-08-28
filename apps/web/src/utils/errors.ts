/** 旧 API 错误信封:{ error: { message } }。
 *  注意:与 api/types 的 ApiError({ code, message })是两种形态;
 *  本文件运行时按信封形态判定('error' in err),故用本地类型。 */
interface LegacyErrorEnvelope {
  error: { message: string };
}

/** 后端不可达时的统一用户文案(空态 / fetch / capability)。 */
export const BACKEND_UNREACHABLE = '无法连接后端服务，请确认后端已启动';

/** 判断是否为 API 错误响应 */
export function isApiError(err: unknown): err is LegacyErrorEnvelope {
  return (
    typeof err === 'object' &&
    err !== null &&
    'error' in err &&
    typeof (err as LegacyErrorEnvelope).error?.message === 'string'
  );
}

/** 从未知错误中提取用户可读消息 */
export function extractErrorMessage(err: unknown): string {
  if (isApiError(err)) {
    return err.error.message;
  }
  if (err instanceof TypeError && /fetch|network|Failed to fetch/i.test(err.message)) {
    return BACKEND_UNREACHABLE;
  }
  if (err instanceof Error) {
    if (/Failed to fetch|NetworkError|Load failed/i.test(err.message)) {
      return BACKEND_UNREACHABLE;
    }
    return err.message;
  }
  return '未知错误，请重试';
}
