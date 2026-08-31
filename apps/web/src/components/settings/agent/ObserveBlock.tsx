import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { AUTO_INDEX_KEY } from './constants';
import type { SettingItem } from './types';

/** 观察自动建索引开关 */
export function ObserveBlock() {
  const addToast = useUIStore((s) => s.addToast);
  const [autoIndex, setAutoIndex] = useState<boolean | null>(null);
  const [autoIndexLoadFailed, setAutoIndexLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem<boolean>>('settings', 'get_setting', { key: AUTO_INDEX_KEY })
      .then((item) => {
        if (alive) setAutoIndex(Boolean(item.value ?? item.default ?? false));
      })
      .catch(() => {
        if (alive) setAutoIndexLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const saveAutoIndex = (next: boolean) => {
    const prev = autoIndex;
    setAutoIndex(next);
    callCapability<SettingItem<boolean>>('settings', 'set_setting', { key: AUTO_INDEX_KEY, value: next })
      .then(() => {
        addToast({
          type: 'success',
          message: next
            ? '已开启:新资源就绪后自动建立图谱索引'
            : '已关闭:只在对话里提示,不自动建索引',
        });
      })
      .catch((err) => {
        setAutoIndex(prev);
        addToast({ type: 'error', message: `保存自动建索引开关失败：${extractErrorMessage(err)}` });
      });
  };

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">观察</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        资源导入完成后 Agent 会观察并在对话里给一句提示；是否顺手建图谱索引由你决定。
      </p>
      {autoIndexLoadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>读取失败请刷新。</p>
      ) : (
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
          <input
            type="checkbox"
            checked={autoIndex ?? false}
            disabled={autoIndex === null}
            onChange={(e) => saveAutoIndex(e.target.checked)}
            aria-label="导入完成后自动建图谱索引"
          />
          导入完成后自动建图谱索引
        </label>
      )}
    </div>
  );
}
