import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import {
  numericDraft,
  ROUNDS_MAX_KEY,
  ROUNDS_RE_MAX,
  ROUNDS_TOOL_KEY,
  ROUNDS_TOOL_MAX,
} from './constants';
import type { SettingItem } from './types';

/** 轮数上限(agent.rounds.*):ReAct 推理轮数与工具调用次数的全局上限 */
export function RoundsBlock() {
  const addToast = useUIStore((s) => s.addToast);

  const [roundsRe, setRoundsRe] = useState('');
  const [roundsTool, setRoundsTool] = useState('');
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem<number>>('settings', 'get_setting', { key: ROUNDS_MAX_KEY })
      .then((item) => {
        if (alive) setRoundsRe(numericDraft(item));
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    callCapability<SettingItem<number>>('settings', 'get_setting', { key: ROUNDS_TOOL_KEY })
      .then((item) => {
        if (alive) setRoundsTool(numericDraft(item));
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const saveRound = (key: string, draft: string, max: number, label: string) => {
    const n = Number(draft);
    if (!Number.isInteger(n) || n < 1 || n > max) {
      addToast({ type: 'warning', message: `${label}须为 1–${max} 的整数` });
      return;
    }
    callCapability<SettingItem<number>>('settings', 'set_setting', { key, value: n })
      .then(() => {
        addToast({ type: 'success', message: `${label}已保存，下一句对话 / 下一单任务生效` });
      })
      .catch((err) => {
        addToast({ type: 'error', message: `保存${label}失败：${extractErrorMessage(err)}` });
      });
  };

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">轮数上限</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        ReAct 推理轮数与工具调用次数的全局上限。对话每回合与任务派出都会读取，改完下一句对话 / 下一单任务生效。
      </p>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>读取失败请刷新。</p>
      ) : (
        <>
          <div className="memory-form-row">
            <span className="muted" style={{ fontSize: 12 }}>ReAct 轮数</span>
            <input
              className="field input"
              type="number"
              min={1}
              max={ROUNDS_RE_MAX}
              style={{ maxWidth: 120 }}
              value={roundsRe}
              onChange={(e) => setRoundsRe(e.target.value)}
              onBlur={() => saveRound(ROUNDS_MAX_KEY, roundsRe, ROUNDS_RE_MAX, 'ReAct 轮数')}
              aria-label="ReAct 轮数上限"
            />
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={() => saveRound(ROUNDS_MAX_KEY, roundsRe, ROUNDS_RE_MAX, 'ReAct 轮数')}
            >
              保存
            </button>
          </div>
          <div className="memory-form-row">
            <span className="muted" style={{ fontSize: 12 }}>工具调用轮数</span>
            <input
              className="field input"
              type="number"
              min={1}
              max={ROUNDS_TOOL_MAX}
              style={{ maxWidth: 120 }}
              value={roundsTool}
              onChange={(e) => setRoundsTool(e.target.value)}
              onBlur={() => saveRound(ROUNDS_TOOL_KEY, roundsTool, ROUNDS_TOOL_MAX, '工具调用轮数')}
              aria-label="工具调用轮数上限"
            />
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={() => saveRound(ROUNDS_TOOL_KEY, roundsTool, ROUNDS_TOOL_MAX, '工具调用轮数')}
            >
              保存
            </button>
          </div>
        </>
      )}
    </div>
  );
}
