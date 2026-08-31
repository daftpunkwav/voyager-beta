import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { APP_ALLOWED_KEY, APP_DENIED_KEY } from './constants';
import type { SettingItem } from './types';

/** 应用内 capability 允许/拒绝名单(phase-19,§9.9) */
export function AppPolicyBlock() {
  const addToast = useUIStore((s) => s.addToast);

  const [allowedDraft, setAllowedDraft] = useState('');
  const [deniedDraft, setDeniedDraft] = useState('');
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    Promise.all([
      callCapability<SettingItem<string[]>>('settings', 'get_setting', { key: APP_ALLOWED_KEY }),
      callCapability<SettingItem<string[]>>('settings', 'get_setting', { key: APP_DENIED_KEY }),
    ])
      .then(([allowed, denied]) => {
        if (!alive) return;
        setAllowedDraft((allowed.value ?? allowed.default ?? ['*']).join('\n'));
        setDeniedDraft((denied.value ?? denied.default ?? []).join('\n'));
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const parseLines = (raw: string) =>
    raw
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);

  const validateLine = (line: string): string | null => {
    if (line === '*') return null;
    if (line.includes('://') || line.includes('/') || line.includes('\\')) {
      return `「${line}」含路径或协议分隔符，只能填能力名`;
    }
    if (line.includes('..')) return `「${line}」不能包含 ..`;
    if (line.includes(' ')) return `「${line}」不能包含空格`;
    if (/[A-Z]/.test(line)) return `「${line}」不能包含大写字母`;
    if (!/^[a-z][a-z0-9_]*(?:\*?|\__[a-z][a-z0-9_]*(?:\*?))$/.test(line)) {
      return `「${line}」不是合法的能力名`;
    }
    return null;
  };

  const save = (key: string, draft: string, label: string, allowEmpty: boolean) => {
    const lines = parseLines(draft);
    if (!allowEmpty && lines.length === 0) {
      addToast({ type: 'warning', message: `${label}不能为空；至少保留 * 或一个具体能力名` });
      return;
    }
    for (const line of lines) {
      const err = validateLine(line);
      if (err) {
        addToast({ type: 'warning', message: err });
        return;
      }
    }
    callCapability<SettingItem<string[]>>('settings', 'set_setting', { key, value: lines })
      .then(() => {
        if (key === APP_ALLOWED_KEY) setAllowedDraft(lines.join('\n'));
        else setDeniedDraft(lines.join('\n'));
        addToast({ type: 'success', message: `${label}已保存，下一轮能力调用即生效` });
      })
      .catch((err) => {
        addToast({ type: 'error', message: `保存${label}失败：${extractErrorMessage(err)}` });
      });
  };

  const saveAllowed = () => save(APP_ALLOWED_KEY, allowedDraft, '应用内能力允许名单', false);
  const saveDenied = () => save(APP_DENIED_KEY, deniedDraft, '应用内能力拒绝名单', true);

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">应用内能力</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        控制 Agent 能否调用笔记、图谱等应用内能力。名称与团队页工具面一致（如 notes__create_note）。单独一行
        * 表示全部应用内能力；notes__* 表示该域前缀；拒绝优先于允许。空白允许名单会让笔记/图谱等桥工具全部失败。
        文件、联网、命令、外接 MCP 不走本名单。
      </p>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>读取失败请刷新。</p>
      ) : (
        <>
          <p className="muted" style={{ fontSize: 12, margin: '8px 0 4px' }}>允许名单（一行一个）：</p>
          <textarea
            className="field input agent-guideline-textarea"
            rows={3}
            value={allowedDraft}
            onChange={(e) => setAllowedDraft(e.target.value)}
            onBlur={saveAllowed}
            placeholder={'*\nnotes__create_note'}
            aria-label="应用内能力允许名单"
          />
          <div className="agent-guideline-meta">
            <span className="muted">{parseLines(allowedDraft).length} 个条目</span>
            <button type="button" className="btn btn-sm btn-ghost" onClick={saveAllowed}>
              保存
            </button>
          </div>

          <p className="muted" style={{ fontSize: 12, margin: '12px 0 4px' }}>拒绝名单（一行一个）：</p>
          <textarea
            className="field input agent-guideline-textarea"
            rows={3}
            value={deniedDraft}
            onChange={(e) => setDeniedDraft(e.target.value)}
            onBlur={saveDenied}
            placeholder={'notes__delete_note\ngraph__*'}
            aria-label="应用内能力拒绝名单"
          />
          <div className="agent-guideline-meta">
            <span className="muted">{parseLines(deniedDraft).length} 个条目</span>
            <button type="button" className="btn btn-sm btn-ghost" onClick={saveDenied}>
              保存
            </button>
          </div>
        </>
      )}
    </div>
  );
}
