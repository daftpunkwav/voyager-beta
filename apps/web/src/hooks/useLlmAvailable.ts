/** LLM 可用性探测(§9.18,phase-12):对话主场用 llm.list_providers 判断有没有
 *  enabled && has_api_key 的提供商——与设置页 !anyUsable / 后端 ServiceLLM 同一真相,
 *  不读旧 settings blob 的 llm_configured。
 *
 *  只有 missing(确认无可用 key)才让调用方显示空态并禁发送;
 *  checking / unknown(查询失败,如网络抖动)不锁死对话——发送仍可用,
 *  由后端 ServiceLLM 的降级句兜底,避免网抖时对话被误关。
 */

import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import type { LlmProvider } from '@/api/types';

export type LlmAvailability = 'checking' | 'ok' | 'missing' | 'unknown';

export function useLlmAvailable(): LlmAvailability {
  const [state, setState] = useState<LlmAvailability>('checking');

  useEffect(() => {
    let alive = true;
    callCapability<LlmProvider[]>('llm', 'list_providers')
      .then((list) => {
        if (!alive) return;
        const usable = Array.isArray(list) && list.some((p) => p.enabled && p.has_api_key);
        setState(usable ? 'ok' : 'missing');
      })
      .catch(() => {
        if (alive) setState('unknown');
      });
    return () => {
      alive = false;
    };
  }, []);

  return state;
}
