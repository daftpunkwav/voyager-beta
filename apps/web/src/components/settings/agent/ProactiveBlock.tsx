import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import {
  PROACTIVE_FOLLOW_UP_MAX,
  PROACTIVE_FOLLOW_UP_MAX_KEY,
  PROACTIVE_PER_DAY_KEY,
  PROACTIVE_PER_DAY_MAX,
  PROACTIVE_PER_SESSION_KEY,
  PROACTIVE_PER_SESSION_MAX,
  PROACTIVE_QUIET_END_KEY,
  PROACTIVE_QUIET_END_MAX,
  PROACTIVE_QUIET_START_KEY,
  PROACTIVE_QUIET_START_MAX,
} from './constants';
import type { SettingItem } from './types';

/** 主动触达预算(§9.8):每会话/每日上限、追问链、安静时段。 */
export function ProactiveBlock() {
  const addToast = useUIStore((s) => s.addToast);

  const [perSession, setPerSession] = useState('');
  const [perDay, setPerDay] = useState('');
  const [followUpMax, setFollowUpMax] = useState('');
  const [quietStart, setQuietStart] = useState('');
  const [quietEnd, setQuietEnd] = useState('');
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    const pull = <T,>(key: string, setter: (v: string) => void) =>
      callCapability<SettingItem<T>>('settings', 'get_setting', { key })
        .then((item) => {
          if (!alive) return;
          const n = Number(item.value ?? item.default);
          setter(Number.isFinite(n) ? String(n) : '');
        })
        .catch(() => {
          if (!alive) return;
          setLoadFailed(true);
        });

    pull<number>(PROACTIVE_PER_SESSION_KEY, setPerSession);
    pull<number>(PROACTIVE_PER_DAY_KEY, setPerDay);
    pull<number>(PROACTIVE_FOLLOW_UP_MAX_KEY, setFollowUpMax);
    pull<number>(PROACTIVE_QUIET_START_KEY, setQuietStart);
    pull<number>(PROACTIVE_QUIET_END_KEY, setQuietEnd);

    return () => {
      alive = false;
    };
  }, []);

    const saveInt = (
    key: string,
    draft: string,
    min: number,
    max: number,
    label: string,
  ) => {
    const n = Number(draft);
    // 空串 Number('')===0,不能当「填 0 关闭」;用户要关须显式输入 0
    if (draft.trim() === '' || !Number.isInteger(n) || n < min || n > max) {
      addToast({ type: 'warning', message: `${label}须为 ${min}–${max} 的整数` });
      return;
    }
    callCapability<SettingItem<number>>('settings', 'set_setting', { key, value: n })
      .then(() => {
        addToast({ type: 'success', message: `${label}已保存，下一条主动消息生效` });
      })
      .catch((err) => {
        addToast({ type: 'error', message: `保存${label}失败：${extractErrorMessage(err)}` });
      });
  };

  const row = (
    label: string,
    value: string,
    setValue: (v: string) => void,
    key: string,
    min: number,
    max: number,
  ) => (
    <div className="memory-form-row" key={key}>
      <span className="muted" style={{ fontSize: 12, minWidth: 100 }}>
        {label}
      </span>
      <input
        className="field input"
        type="number"
        min={min}
        max={max}
        style={{ maxWidth: 120 }}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => saveInt(key, value, min, max, label)}
        aria-label={label}
      />
      <button
        type="button"
        className="btn btn-sm btn-ghost"
        onClick={() => saveInt(key, value, min, max, label)}
      >
        保存
      </button>
    </div>
  );

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">主动触达</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        问候在打开应用时出现；没回复会按链追问。每会话上限填 0 关闭问候与追问；追问链上限填 0
        只问候不追问。改完立即生效，不用重启。
      </p>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>读取失败请刷新。</p>
      ) : (
        <>
          {row(
            '每会话上限',
            perSession,
            setPerSession,
            PROACTIVE_PER_SESSION_KEY,
            0,
            PROACTIVE_PER_SESSION_MAX,
          )}
          {row(
            '每日上限',
            perDay,
            setPerDay,
            PROACTIVE_PER_DAY_KEY,
            0,
            PROACTIVE_PER_DAY_MAX,
          )}
          {row(
            '追问链上限',
            followUpMax,
            setFollowUpMax,
            PROACTIVE_FOLLOW_UP_MAX_KEY,
            0,
            PROACTIVE_FOLLOW_UP_MAX,
          )}
          <p className="muted" style={{ fontSize: 12, margin: '12px 0 4px' }}>
            安静时段（本地小时，可跨午夜，例如 23→7）
          </p>
          {row(
            '开始',
            quietStart,
            setQuietStart,
            PROACTIVE_QUIET_START_KEY,
            0,
            PROACTIVE_QUIET_START_MAX,
          )}
          {row(
            '结束',
            quietEnd,
            setQuietEnd,
            PROACTIVE_QUIET_END_KEY,
            0,
            PROACTIVE_QUIET_END_MAX,
          )}
        </>
      )}
    </div>
  );
}
