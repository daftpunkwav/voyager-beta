import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { RETENTION_KEY, RETENTION_MAX } from './constants';
import type { SettingItem } from './types';

/** 情节保留天数(agent.memory.retention_days):从记忆查看块拆出的独立设置块 */
export function MemoryRetentionBlock() {
  const addToast = useUIStore((s) => s.addToast);
  const [retention, setRetention] = useState('');

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem<number>>('settings', 'get_setting', { key: RETENTION_KEY })
      .then((item) => {
        if (alive) setRetention(String(item.value ?? item.default ?? 0));
      })
      .catch(() => {
        /* 读取失败留空草稿,不拦记忆区 */
      });
    return () => {
      alive = false;
    };
  }, []);

  const saveRetention = () => {
    const n = Number(retention);
    if (!Number.isInteger(n) || n < 0 || n > RETENTION_MAX) {
      addToast({ type: 'warning', message: `保留天数须为 0–${RETENTION_MAX} 的整数，0 表示交给 Agent 管理` });
      return;
    }
    callCapability<SettingItem<number>>('settings', 'set_setting', { key: RETENTION_KEY, value: n })
      .then(() => {
        addToast({
          type: 'success',
          message:
            n > 0
              ? `情节记忆保留 ${n} 天，打开本页时清理更早情节`
              : '已交给 Agent 管理，不再按天清理',
        });
      })
      .catch((err) => {
        addToast({ type: 'error', message: `保存保留天数失败：${extractErrorMessage(err)}` });
      });
  };

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">情节保留天数</h3>
      <div className="memory-form-row">
        <input
          className="field input"
          type="number"
          min={0}
          max={RETENTION_MAX}
          style={{ maxWidth: 120 }}
          value={retention}
          onChange={(e) => setRetention(e.target.value)}
          onBlur={saveRetention}
          aria-label="情节记忆保留天数"
        />
        <button type="button" className="btn btn-sm btn-ghost" onClick={saveRetention}>
          保存
        </button>
      </div>
      <p className="muted" style={{ fontSize: 12 }}>
        0 = 不按天自动清（交给 Agent 管理）；大于 0 = 打开本页时清理超过天数的情节。
      </p>
    </div>
  );
}
