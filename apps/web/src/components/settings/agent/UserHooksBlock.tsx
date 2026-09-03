import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import type { UserHookItem, UserHooksReloadResult } from './types';

/** 用户钩子(phase-78):workspace/hooks/ 下的声明式 hook json,增删改文件后
 *  点「重新加载」即时生效(免重启);已批准插件的钩子不受重载影响。 */
export function UserHooksBlock() {
  const addToast = useUIStore((s) => s.addToast);
  const [items, setItems] = useState<UserHookItem[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reloading, setReloading] = useState(false); // busy 防双提交

  const refresh = () =>
    callCapability<{ items: UserHookItem[] }>('agent', 'list_user_hooks', {})
      .then((out) => setItems(Array.isArray(out?.items) ? out.items : []))
      .catch(() => undefined); // 操作后刷新失败:静默保留现列表,toast 由调用方负责

  useEffect(() => {
    let alive = true;
    callCapability<{ items: UserHookItem[] }>('agent', 'list_user_hooks', {})
      .then((out) => {
        if (alive) setItems(Array.isArray(out?.items) ? out.items : []);
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const onReload = async () => {
    if (reloading) return;
    setReloading(true);
    try {
      const res = await callCapability<UserHooksReloadResult>('agent', 'reload_user_hooks', {});
      let message = `已重新加载用户钩子：装载 ${res.loaded} 个`;
      if (res.skipped && res.skipped.length > 0) {
        const detail = res.skipped.map((s) => `${s.path}（${s.reason}）`).join('、');
        message += `；跳过无法解析的文件：${detail}`;
      }
      addToast({ type: 'success', message });
      await refresh();
    } catch (err) {
      addToast({ type: 'error', message: `重载失败：${extractErrorMessage(err)}` });
    } finally {
      setReloading(false);
    }
  };

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">用户钩子</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        工作目录 hooks/ 下的声明式钩子（JSON 文件，on + enabled）。增删改文件后点
        「重新加载」立即生效，无需重启开发服务；已批准插件的钩子不受影响。
      </p>
      <div style={{ marginBottom: 12 }}>
        <button
          type="button"
          className="btn btn-sm btn-primary"
          aria-label="重新加载用户钩子"
          disabled={reloading}
          onClick={() => void onReload()}
        >
          {reloading ? '重载中…' : '重新加载'}
        </button>
      </div>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>读取失败请刷新。</p>
      ) : items === null ? (
        <p className="muted" style={{ fontSize: 12 }}>用户钩子清单加载中…</p>
      ) : items.length === 0 ? (
        <p className="muted" style={{ fontSize: 12 }}>
          还没有用户钩子。把 JSON 文件放到工作目录的 hooks/ 下（例:{' '}
          {'{ "on": "note.created", "enabled": true }'}），再点上方「重新加载」。
        </p>
      ) : (
        <ul className="memory-entry-list">
          {items.map((h) => (
            <li key={h.path} className="memory-entry">
              <span className="memory-kind">{h.path}</span>
              <span className="memory-entry-summary">
                {h.on || '（无法解析）'}
                {h.enabled ? '' : ' · 已停用'}
                {h.loaded ? '' : ' · 未装载'}
              </span>
              <span className="muted" style={{ fontSize: 12 }}>{h.description}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
