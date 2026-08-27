/** 旧 API 错误信封:{ error: { message } }。
 *  注意:与 api/types 的 ApiError({ code, message })是两种形态;
 *  本文件运行时按信封形态判定('error' in err),故用本地类型。 */
interface LegacyErrorEnvelope {
  error: { message: string };
}

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
  // 网络错误统一提示，不硬编码端口（端口可通过 VITE_API_TARGET 等环境变量覆盖）
  const NETWORK_HINT = '无法连接后端，请确认 API 服务已启动且端口配置正确（开发默认经 Vite 代理转发）';
  if (err instanceof TypeError && /fetch|network|Failed to fetch/i.test(err.message)) {
    return NETWORK_HINT;
  }
  if (err instanceof Error) {
    if (/Failed to fetch|NetworkError|Load failed/i.test(err.message)) {
      return NETWORK_HINT;
    }
    return err.message;
  }
  return '未知错误，请重试';
}
