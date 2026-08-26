/** Voyager `IApiClient` 形态兼容入口(单例 getApi,与桥接层 legacyApi 一一对应)。
 *
 * 目的:让已迁移的 10 个 page / 9 个 hook(react-query 形态)无需改 import,
 * 仍能调用原 84 个方法,内部走 voyager 的 capability 框架(bridge/legacyApi.ts)。
 *
 * 不属于架构铁律,仅作过渡;新代码禁止引用本文件,
 * 应直接用 @/bridge/client 的 callCapability。
 *
 * 配套:
 *  - 旧 api/types 走 ./types
 *  - 旧 api/real/http.ts 已删除;旧 import 改指本文件,getApi() / clearLegacyTokenStorage 已 re-export。
 *
 * 重要:`getApi()` 不违反"一份 Action 模型"(铁律 2),
 * 因为 legacyApi.ts 内部 84 个方法全部走 callCapability;
 * 新代码仍应优先用 `callCapability`,语义更明确、不绕桥接层。
 */

export {
  getLegacyApi as getApi,
  LegacyApiClient as RealApiClient,
  ApiRequestError,
  ERROR_CODES,
  type ApiResponse,
  type SSEEvent,
} from '@/bridge/legacyApi';

// 旧 store 兼容 import 用
export type { IApiClient } from '@/api/types';

// 旧 API 形态:MockApiClient 仅在 VITE_USE_MOCK=true 时启用(由 main.tsx 选);此处不再提供 mock 入口。

/** 旧版 token 清理(供 authStore 兼容调用;voyager 已改用 cookie session)。 */
export function clearLegacyTokenStorage(): void {
  try {
    if (typeof localStorage === 'undefined') return;
    for (const k of ['voyager_token', 'voyager_session', 'token', 'session']) {
      localStorage.removeItem(k);
    }
  } catch {
    /* noop */
  }
}
