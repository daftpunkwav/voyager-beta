import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { GlassSelect } from '@/components/common/GlassSelect';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import {
  NETWORK_DOMAINS_KEY,
  NETWORK_MODE_KEY,
  NETWORK_MODE_OPTIONS,
  numericDraft,
  ROUNDS_MAX_KEY,
  ROUNDS_RE_MAX,
  ROUNDS_TOOL_KEY,
  ROUNDS_TOOL_MAX,
  WORKDIR_KEY,
} from './constants';
import type { SettingItem } from './types';

/** 轮数上限 + 网络权限 + 工作目录 */
export function LimitsBlock() {
  const addToast = useUIStore((s) => s.addToast);

  const [roundsRe, setRoundsRe] = useState('');
  const [roundsTool, setRoundsTool] = useState('');
  const [limitsLoadFailed, setLimitsLoadFailed] = useState(false);

  const [netMode, setNetMode] = useState<string | null>(null);
  const [domainsDraft, setDomainsDraft] = useState('');
  const [netLoadFailed, setNetLoadFailed] = useState(false);

  const [workdir, setWorkdir] = useState('');
  const [workdirLoadFailed, setWorkdirLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem<number>>('settings', 'get_setting', { key: ROUNDS_MAX_KEY })
      .then((item) => {
        if (alive) setRoundsRe(numericDraft(item));
      })
      .catch(() => {
        if (alive) setLimitsLoadFailed(true);
      });
    callCapability<SettingItem<number>>('settings', 'get_setting', { key: ROUNDS_TOOL_KEY })
      .then((item) => {
        if (alive) setRoundsTool(numericDraft(item));
      })
      .catch(() => {
        if (alive) setLimitsLoadFailed(true);
      });
    callCapability<SettingItem<string>>('settings', 'get_setting', { key: NETWORK_MODE_KEY })
      .then((item) => {
        if (alive) setNetMode(item.value ?? item.default ?? 'whitelist');
      })
      .catch(() => {
        if (alive) setNetLoadFailed(true);
      });
    callCapability<SettingItem<string[]>>('settings', 'get_setting', { key: NETWORK_DOMAINS_KEY })
      .then((item) => {
        if (alive) setDomainsDraft((item.value ?? item.default ?? []).join('\n'));
      })
      .catch(() => {
        if (alive) setNetLoadFailed(true);
      });
    callCapability<SettingItem<string>>('settings', 'get_setting', { key: WORKDIR_KEY })
      .then((item) => {
        if (alive) setWorkdir(item.value ?? item.default ?? '');
      })
      .catch(() => {
        if (alive) setWorkdirLoadFailed(true);
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

  const saveNetworkMode = (mode: string) => {
    const prev = netMode;
    setNetMode(mode);
    callCapability<SettingItem<string>>('settings', 'set_setting', { key: NETWORK_MODE_KEY, value: mode })
      .then(() => {
        addToast({ type: 'success', message: '网络权限已保存，下一轮联网判定即生效' });
      })
      .catch((err) => {
        setNetMode(prev);
        addToast({ type: 'error', message: `保存网络权限失败：${extractErrorMessage(err)}` });
      });
  };

  const saveDomains = () => {
    const lines = domainsDraft
      .split('\n')
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean);
    const bad = lines.find((line) => line.includes('://') || line.includes('/'));
    if (bad) {
      addToast({ type: 'warning', message: `「${bad}」不是域名：一行填一个 host（如 github.com），不带协议与路径` });
      return;
    }
    callCapability<SettingItem<string[]>>('settings', 'set_setting', {
      key: NETWORK_DOMAINS_KEY,
      value: lines,
    })
      .then(() => {
        setDomainsDraft(lines.join('\n'));
        addToast({ type: 'success', message: `白名单已保存（${lines.length} 个域名），下一轮联网判定即生效` });
      })
      .catch((err) => {
        addToast({ type: 'error', message: `保存白名单失败：${extractErrorMessage(err)}` });
      });
  };

  const saveWorkdir = () => {
    const next = workdir.trim();
    if (next.split(/[\\/]+/).includes('..')) {
      addToast({ type: 'warning', message: '工作目录不允许包含 .. 段' });
      return;
    }
    callCapability<SettingItem<string>>('settings', 'set_setting', { key: WORKDIR_KEY, value: next })
      .then(() => {
        setWorkdir(next);
        addToast({ type: 'success', message: '已保存。重启开发服务后，文件工具与资源库会用新目录。' });
      })
      .catch((err) => {
        addToast({ type: 'error', message: `保存工作目录失败：${extractErrorMessage(err)}` });
      });
  };

  return (
    <>
      <div className="agent-settings-block">
        <h3 className="agent-settings-subtitle">轮数上限</h3>
        <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
          ReAct 推理轮数与工具调用次数的全局上限。对话每回合与任务派出都会读取，改完下一句对话 / 下一单任务生效。
        </p>
        {limitsLoadFailed ? (
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

      <div className="agent-settings-block">
        <h3 className="agent-settings-subtitle">网络权限</h3>
        <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
          控制 Agent 联网抓取的档位；下一轮联网判定即生效，无需重启。
        </p>
        {netLoadFailed ? (
          <p className="muted" style={{ fontSize: 12 }}>读取失败请刷新。</p>
        ) : (
          <>
            <GlassSelect
              size="sm"
              value={netMode ?? ''}
              options={
                netMode === null
                  ? [{ value: '', label: '读取中…' }]
                  : NETWORK_MODE_OPTIONS.some((o) => o.value === netMode)
                    ? NETWORK_MODE_OPTIONS
                    : [...NETWORK_MODE_OPTIONS, { value: netMode, label: netMode }]
              }
              onChange={(v) => saveNetworkMode(v)}
              aria-label="网络权限模式"
            />
            <p className="muted" style={{ fontSize: 12, margin: '8px 0 4px' }}>
              白名单域名(一行一个,如 github.com):
            </p>
            <textarea
              className="field input agent-guideline-textarea"
              rows={3}
              value={domainsDraft}
              disabled={netMode !== 'whitelist'}
              onChange={(e) => setDomainsDraft(e.target.value)}
              onBlur={saveDomains}
              placeholder={'github.com\narxiv.org'}
              aria-label="白名单域名"
            />
            <div className="agent-guideline-meta">
              <span className="muted">{domainsDraft.split('\n').filter((s) => s.trim()).length} 个域名</span>
              <button
                type="button"
                className="btn btn-sm btn-ghost"
                disabled={netMode !== 'whitelist'}
                onClick={saveDomains}
              >
                保存
              </button>
            </div>
          </>
        )}
      </div>

      <div className="agent-settings-block">
        <h3 className="agent-settings-subtitle">工作目录</h3>
        <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
          相对仓库根，默认 workspace；与资源库共用。保存后需重启开发服务才切换。
        </p>
        {workdirLoadFailed ? (
          <p className="muted" style={{ fontSize: 12 }}>读取失败请刷新。</p>
        ) : (
          <div className="memory-form-row">
            <input
              className="field input"
              style={{ maxWidth: 260 }}
              value={workdir}
              onChange={(e) => setWorkdir(e.target.value)}
              onBlur={saveWorkdir}
              placeholder="workspace"
              aria-label="工作目录"
            />
            <button type="button" className="btn btn-sm btn-ghost" onClick={saveWorkdir}>
              保存
            </button>
          </div>
        )}
      </div>
    </>
  );
}
