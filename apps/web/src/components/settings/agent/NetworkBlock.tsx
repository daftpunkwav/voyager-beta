import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { GlassSelect } from '@/components/common/GlassSelect';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import {
  NETWORK_DOMAINS_KEY,
  NETWORK_MODE_KEY,
  NETWORK_MODE_OPTIONS,
} from './constants';
import type { SettingItem } from './types';

/** 网络权限(agent.network.*):联网档位 + 白名单域名,下一轮联网判定即生效 */
export function NetworkBlock() {
  const addToast = useUIStore((s) => s.addToast);

  const [netMode, setNetMode] = useState<string | null>(null);
  const [domainsDraft, setDomainsDraft] = useState('');
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem<string>>('settings', 'get_setting', { key: NETWORK_MODE_KEY })
      .then((item) => {
        if (alive) setNetMode(item.value ?? item.default ?? 'whitelist');
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    callCapability<SettingItem<string[]>>('settings', 'get_setting', { key: NETWORK_DOMAINS_KEY })
      .then((item) => {
        if (alive) setDomainsDraft((item.value ?? item.default ?? []).join('\n'));
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

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

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">网络权限</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        控制 Agent 联网抓取的档位；下一轮联网判定即生效，无需重启。
      </p>
      {loadFailed ? (
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
  );
}
