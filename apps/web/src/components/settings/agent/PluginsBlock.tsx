import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import type { PluginApproveResult, PluginItem } from './types';

/** 权限摘要:scopes 逐个列出,网络/文件档位非空才显示 */
function permissionSummary(p: PluginItem): string {
  const parts: string[] = [];
  if (p.permissions.scopes.length > 0) parts.push(p.permissions.scopes.join('、'));
  if (p.permissions.network) parts.push(`网络 ${p.permissions.network}`);
  if (p.permissions.fs) parts.push(`文件 ${p.permissions.fs}`);
  return parts.length > 0 ? parts.join(' · ') : '未声明权限';
}

/** 插件(§9.13):发现 plugins/ 下的清单;整包批准后其 skill/hook 即装,MCP 只登记待批准条目 */
export function PluginsBlock() {
  const addToast = useUIStore((s) => s.addToast);
  const [plugins, setPlugins] = useState<PluginItem[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busyName, setBusyName] = useState<string | null>(null);

  const reload = () =>
    callCapability<{ items: PluginItem[] }>('agent', 'list_plugins', {})
      .then((out) => setPlugins(Array.isArray(out?.items) ? out.items : []))
      .catch(() => undefined); // 操作后刷新失败:静默保留现列表,toast 由调用方负责

  useEffect(() => {
    let alive = true;
    callCapability<{ items: PluginItem[] }>('agent', 'list_plugins', {})
      .then((out) => {
        if (alive) setPlugins(Array.isArray(out?.items) ? out.items : []);
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const toggle = async (p: PluginItem) => {
    setBusyName(p.name);
    const verb = p.approved ? '撤销' : '批准';
    try {
      const res = await callCapability<PluginApproveResult>('agent', 'set_plugin_approval', {
        name: p.name,
        approved: !p.approved,
      });
      addToast({
        type: 'success',
        message: p.approved
          ? `已撤销插件「${res.name}」，其技能与钩子已从系统移除`
          : `已批准插件「${res.name}」：技能 ${res.loaded.skills.length} 个、钩子 ${res.loaded.hooks} 个已装载` +
            (res.loaded.mcp_registered > 0
              ? `；${res.loaded.mcp_registered} 条 MCP 配置已登记，工具还需在「外接 MCP」里批准`
              : ''),
      });
      await reload();
    } catch (err) {
      addToast({ type: 'error', message: `${verb}失败：${extractErrorMessage(err)}` });
    } finally {
      setBusyName(null);
    }
  };

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">插件</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        仓库根 plugins/ 下的声明式插件。整包批准后它的技能与钩子进入系统；随插件的 MCP
        配置只会登记为待批准条目，工具仍需在外接 MCP 里逐台批准。
      </p>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>读取失败请刷新。</p>
      ) : plugins === null ? (
        <p className="muted" style={{ fontSize: 12 }}>插件清单加载中…</p>
      ) : plugins.length === 0 ? (
        <p className="muted" style={{ fontSize: 12 }}>
          还没有发现插件。把含 plugin.json 的插件目录放进仓库根的 plugins/ 下即可出现在这里。
        </p>
      ) : (
        <ul className="memory-entry-list">
          {plugins.map((p) => (
            <li key={p.path} className="memory-entry">
              <span className="memory-kind">
                {p.name}
                {p.version ? ` v${p.version}` : ''}
              </span>
              {p.description && <span className="memory-entry-summary">{p.description}</span>}
              <span className="memory-entry-summary">
                {p.approved ? '已批准' : '未批准'} · {permissionSummary(p)}
              </span>
              <span className="muted" style={{ fontSize: 12 }}>
                包含：技能 {p.contains.skills} · 钩子 {p.contains.hooks}
                {p.contains.mcp ? ' · MCP 配置' : ''}
              </span>
              <div className="agent-guideline-meta">
                <button
                  type="button"
                  className="btn btn-sm btn-ghost"
                  aria-label={`${p.approved ? '撤销批准' : '批准插件'} ${p.name}`}
                  disabled={busyName === p.name}
                  onClick={() => void toggle(p)}
                >
                  {p.approved ? '撤销批准' : '批准插件'}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
