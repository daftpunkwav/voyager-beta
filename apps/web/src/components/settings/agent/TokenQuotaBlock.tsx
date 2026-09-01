import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { DAILY_TOKENS_KEY, DAILY_TOKENS_MAX, numericDraft } from './constants';
import type { SettingItem } from './types';

/** token 日配额(agent.resource.daily_tokens,§9.9 资源维):当日 UTC 自然日内
 *  所有 LLM 调用的 input+output token 合计上限,0=不限;后端每次 complete 前热读 */
export function TokenQuotaBlock() {
  const addToast = useUIStore((s) => s.addToast);

  const [quota, setQuota] = useState('');
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem<number>>('settings', 'get_setting', { key: DAILY_TOKENS_KEY })
      .then((item) => {
        if (alive) setQuota(numericDraft(item));
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const saveQuota = () => {
    const n = Number(quota);
    // 空串(含纯空白)不是数字,须显式拒绝:Number('')===0 会落进合法域,静默存 0=不限
    // 0 合法且表示不限;其余须为 1..上限 的整数
    if (quota.trim() === '' || !Number.isInteger(n) || n < 0 || n > DAILY_TOKENS_MAX) {
      addToast({ type: 'warning', message: `Token 日配额须为 0–${DAILY_TOKENS_MAX} 的整数（0 表示不限）` });
      return;
    }
    callCapability<SettingItem<number>>('settings', 'set_setting', { key: DAILY_TOKENS_KEY, value: n })
      .then(() => {
        addToast({ type: 'success', message: 'Token 日配额已保存，下一句对话即按新配额生效' });
      })
      .catch((err) => {
        addToast({ type: 'error', message: `保存 Token 日配额失败：${extractErrorMessage(err)}` });
      });
  };

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">Token 日配额</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        当日（UTC 自然日切日）所有 LLM 调用的输入 + 输出 token 合计上限；0 表示不限。保存后下一句对话即按新配额生效。
      </p>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>读取失败请刷新。</p>
      ) : (
        <div className="memory-form-row">
          <span className="muted" style={{ fontSize: 12 }}>每日 token 上限</span>
          <input
            className="field input"
            type="number"
            min={0}
            max={DAILY_TOKENS_MAX}
            style={{ maxWidth: 120 }}
            value={quota}
            onChange={(e) => setQuota(e.target.value)}
            onBlur={saveQuota}
            aria-label="Token 日配额"
          />
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            onClick={saveQuota}
          >
            保存
          </button>
        </div>
      )}
    </div>
  );
}
