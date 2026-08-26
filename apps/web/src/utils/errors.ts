// @ts-nocheck — 迁移期:RepoPilot 风格代码,新 page / hook 仍按 strict 写(见各文件顶部注释)。
import type { ApiError } from '@/api/types';

/** 判断是否为 API 错误响应 */
export function isApiError(err: unknown): err is ApiError {
  return (
    typeof err === 'object' &&
    err !== null &&
    'error' in err &&
    typeof (err as ApiError).error?.message === 'string'
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
