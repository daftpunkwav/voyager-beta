import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { CONDUCT_KEY, CONDUCT_MAX } from './constants';
import type { SettingItem } from './types';

/** 通用行为准则(agent.conduct):对所有 Agent 生效,注入每次对话 system */
export function ConductBlock() {
  const addToast = useUIStore((s) => s.addToast);
  const [conductDraft, setConductDraft] = useState('');
  const [saved, setSaved] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem<string>>('settings', 'get_setting', { key: CONDUCT_KEY })
      .then((item) => {
        if (!alive) return;
        const v = item.value ?? item.default ?? '';
        setConductDraft(v);
        setSaved(v);
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const saveConduct = () => {
    if (saved === null) return;
    const next = conductDraft.slice(0, CONDUCT_MAX);
    if (next === saved) return;
    callCapability<SettingItem<string>>('settings', 'set_setting', { key: CONDUCT_KEY, value: next })
      .then(() => {
        setSaved(next);
        addToast({ type: 'success', message: '通用行为准则已保存' });
      })
      .catch((err) => {
        addToast({ type: 'error', message: `保存通用行为准则失败：${extractErrorMessage(err)}` });
      });
  };

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">通用行为准则</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        对所有 Agent 生效。例如：回答简洁、不要使用 emoji、先确认再改代码。
      </p>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>读取失败请刷新。</p>
      ) : (
        <>
          <textarea
            className="field input agent-guideline-textarea"
            rows={5}
            maxLength={CONDUCT_MAX}
            value={conductDraft}
            onChange={(e) => setConductDraft(e.target.value)}
            onBlur={saveConduct}
            placeholder="写一条所有 Agent 都应遵守的规则…"
            aria-label="通用行为准则"
          />
          <div className="agent-guideline-meta">
            <span className="muted">{conductDraft.length}/{CONDUCT_MAX}</span>
            <button type="button" className="btn btn-sm btn-ghost" onClick={saveConduct}>
              保存
            </button>
          </div>
        </>
      )}
    </div>
  );
}
