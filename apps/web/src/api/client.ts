/** 数据访问统一门面(单例 getApi)· 前端唯一 API 入口。
 *
 * 职责:以 IApiClient 形态(84 个方法,按 agent/source/note/graph/setting/usage/system 分域)
 * 暴露后端能力;实现层是 bridge/legacyApi.ts,每个方法内部走 callCapability(§2.1 一份 Action 模型)。
 *
 * 使用规则(ESLint no-restricted-imports 已固化):
 *  - 页面/组件默认经各域 hooks(如 hooks/useProjects)访问,不要在组件里直连 store;
 *  - 需要直接取数据时 import 本文件(getApi),禁止绕过本文件直引 @/bridge/legacyApi;
 *  - 少数无副作用只读能力(如健康摘要)可用 @/bridge/client 的 callCapability 直调。
 *
 * secret 边界:API key 只允许 USER actor 写,本门面不缓存不透传明文。
 */

import { STORAGE } from '@/brand';

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

/** 旧版 token 清理(供 authStore 兼容调用;本应用已改用 cookie session)。 */
export function clearLegacyTokenStorage(): void {
  try {
    if (typeof localStorage === 'undefined') return;
    for (const k of [STORAGE.legacy.token, STORAGE.legacy.session, 'token', 'session']) {
      localStorage.removeItem(k);
    }
  } catch {
    /* noop */
  }
}
