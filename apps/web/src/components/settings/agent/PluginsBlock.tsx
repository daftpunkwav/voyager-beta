import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import type { PluginApproveResult, PluginItem } from './types';

/** 权限摘要:scopes 逐个列出,网络/文件档位非空才显示(批准前清单强调) */
function permissionSummary(p: PluginItem): string {
  const parts: string[] = [];
  if (p.permissions.scopes.length > 0) parts.push(p.permissions.scopes.join('、'));
  if (p.permissions.network) parts.push(`网络 ${p.permissions.network}`);
  if (p.permissions.fs) parts.push(`文件 ${p.permissions.fs}`);
  return parts.length > 0 ? parts.join(' · ') : '未声明权限';
}

function resultMessage(verb: string, res: PluginApproveResult): string {
  // phase-76:撤销 / 改勾会按安全规则回收该插件登记的外接 MCP,回包披露结果
  const reclaimed = res.mcp_reclaimed ?? [];
  const reclaimSkipped = res.mcp_reclaim_skipped ?? [];
  if (verb === '撤销') {
    let msg = `已撤销插件「${res.name}」，其技能与钩子已从系统移除`;
    if (reclaimed.length > 0) msg += `；已同步移除其外接 MCP：${reclaimed.join('、')}`;
    if (reclaimSkipped.length > 0) {
      const detail = reclaimSkipped.map((s) => `${s.id}（${s.reason}）`).join('、');
      msg += `；未回收：${detail}`;
    }
    return msg;
  }
  const loaded = res.loaded;
  const skipped = res.skipped;
  let msg = `已${verb}插件「${res.name}」：技能 ${loaded.skills.length} 个、钩子 ${loaded.hooks} 个已装载`;
  if (loaded.mcp_registered > 0) {
    msg += `；${loaded.mcp_registered} 条 MCP 配置已登记，工具还需在「外接 MCP」里批准`;
  }
  if (reclaimed.length > 0) msg += `；已移除取消勾选的 MCP：${reclaimed.join('、')}`;
  if (skipped) {
    const n = skipped.skills.length + skipped.hooks.length + skipped.mcp.length;
    if (n > 0) msg += `；${n} 个勾选项当前在插件里不存在，已跳过（勾选会保留，恢复后生效）`;
  }
  return msg;
}

interface PluginRowProps {
  p: PluginItem;
  busy: boolean;
  onBundle: (p: PluginItem) => void;
  onUnapprove: (p: PluginItem) => void;
  onItem: (p: PluginItem, picks: PluginPicks) => void;
}

export interface PluginPicks {
  skills: string[];
  hooks: string[];
  mcp: string[];
}

/** 分项勾选面板:未批准插件展示权限清单 + contains 明细;勾选后「自定义批准」 */
function PluginPicker({
  p,
  busy,
  onCancel,
  onSubmit,
}: {
  p: PluginItem;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (picks: PluginPicks) => void;
}) {
  const [picks, setPicks] = useState<PluginPicks>(() => ({
    skills: p.approved ? p.skills.filter((s) => s.approved).map((s) => s.name) : [],
    hooks: p.approved ? p.hooks.filter((h) => h.approved).map((h) => h.path) : [],
    mcp: p.approved ? p.mcp.filter((m) => m.approved).map((m) => m.id) : [],
  }));
  const anyPicked = picks.skills.length + picks.hooks.length + picks.mcp.length > 0;

  const toggle = (kind: keyof PluginPicks, value: string) => {
    setPicks((prev) => {
      const list = prev[kind];
      const next = list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
      return { ...prev, [kind]: next };
    });
  };

  return (
    <div className="plugin-picker">
      {!p.approved && (
        <p className="muted" style={{ fontSize: 12, margin: '6px 0' }}>
          请求权限：<strong>{permissionSummary(p)}</strong>
        </p>
      )}
      {p.skills.length > 0 && (
        <div className="plugin-picker-group">
          <div className="plugin-picker-label">技能</div>
          {p.skills.map((s) => (
            <label key={s.name} className="plugin-picker-option">
              <input
                type="checkbox"
                checked={picks.skills.includes(s.name)}
                onChange={() => toggle('skills', s.name)}
              />
              {s.name}
            </label>
          ))}
        </div>
      )}
      {p.hooks.length > 0 && (
        <div className="plugin-picker-group">
          <div className="plugin-picker-label">钩子</div>
          {p.hooks.map((h) => (
            <label key={h.path} className="plugin-picker-option">
              <input
                type="checkbox"
                checked={picks.hooks.includes(h.path)}
                onChange={() => toggle('hooks', h.path)}
              />
              {h.on}
              {h.enabled ? '' : '（默认停用）'}
            </label>
          ))}
        </div>
      )}
      {p.mcp.length > 0 && (
        <div className="plugin-picker-group">
          <div className="plugin-picker-label">MCP server</div>
          {p.mcp.map((m) => (
            <label key={m.id} className="plugin-picker-option">
              <input
                type="checkbox"
                checked={picks.mcp.includes(m.id)}
                onChange={() => toggle('mcp', m.id)}
              />
              {m.id}
              {m.registered ? '（已登记，工具待批准）' : ''}
            </label>
          ))}
        </div>
      )}
      {p.mcp.length > 0 && (
        <p className="muted" style={{ fontSize: 11, margin: '4px 0 0' }}>
          勾选 MCP 只会登记为待批准条目，工具仍需在外接 MCP 里批准。
        </p>
      )}
      <div className="plugin-picker-actions">
        <button
          type="button"
          className="btn btn-sm btn-primary"
          disabled={busy || !anyPicked}
          onClick={() => onSubmit(picks)}
        >
          自定义批准
        </button>
        <button type="button" className="btn btn-sm btn-ghost" disabled={busy} onClick={onCancel}>
          取消
        </button>
      </div>
      {!anyPicked && (
        <p className="muted" style={{ fontSize: 11, margin: '4px 0 0' }}>
          至少要勾选一项（技能 / 钩子 / MCP）。
        </p>
      )}
    </div>
  );
}

/** 插件(§9.13):发现 plugins/ 下的清单;整包或分项批准后其 skill/hook 即装,MCP 只登记待批准条目 */
export function PluginsBlock() {
  const addToast = useUIStore((s) => s.addToast);
  const [plugins, setPlugins] = useState<PluginItem[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busyName, setBusyName] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null); // 正在分项勾选的插件名

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

  const run = async (verb: '批准' | '撤销', p: PluginItem, args: Record<string, unknown>) => {
    setBusyName(p.name);
    try {
      const res = await callCapability<PluginApproveResult>('agent', 'set_plugin_approval', {
        name: p.name,
        approved: verb !== '撤销',
        ...args,
      });
      addToast({ type: 'success', message: resultMessage(verb, res) });
      setEditing(null);
      await reload();
    } catch (err) {
      addToast({ type: 'error', message: `${verb}失败：${extractErrorMessage(err)}` });
    } finally {
      setBusyName(null);
    }
  };

  const onBundle = (p: PluginItem) => void run('批准', p, { granularity: 'bundle' });
  const onUnapprove = (p: PluginItem) => {
    // phase-76(选型 S3):撤销会回收其登记、尚未批准任何工具的外接 MCP;
    // 工具已批准或他插件共用的由后端保留,结果在 toast 里披露。confirm 列出将回收的候选。
    const reclaimable = p.mcp
      .filter((m) => m.registered && m.tools_approved.length === 0)
      .map((m) => m.id);
    const note =
      reclaimable.length > 0 ? `撤销后将同时移除其登记的外接 MCP：${reclaimable.join('、')}。` : '';
    if (!window.confirm(`撤销批准「${p.name}」？其技能与钩子将立即卸载。${note}`)) return;
    void run('撤销', p, { granularity: 'bundle' });
  };
  const onItem = (p: PluginItem, picks: PluginPicks) =>
    void run('批准', p, { granularity: 'item', skills: picks.skills, hooks: picks.hooks, mcp: picks.mcp });

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">插件</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        仓库根 plugins/ 下的声明式插件。整包批准后它的技能与钩子进入系统；也可以展开逐项勾选。
        随插件的 MCP 配置只会登记为待批准条目，工具仍需在外接 MCP 里逐台批准；
        撤销批准时会同步移除其登记、且工具还没批准过的外接 MCP（已批准工具的保留）。
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
                {p.approved
                  ? `已批准（${p.granularity === 'item' ? '自定义分项' : '整包'}）`
                  : '未批准'}{' '}
                · 请求权限：{permissionSummary(p)}
              </span>
              <span className="muted" style={{ fontSize: 12 }}>
                包含：技能 {p.contains.skills} · 钩子 {p.contains.hooks}
                {p.contains.mcp ? ' · MCP 配置' : ''}
              </span>
              {editing === p.name ? (
                <PluginPicker
                  p={p}
                  busy={busyName === p.name}
                  onCancel={() => setEditing(null)}
                  onSubmit={(picks) => onItem(p, picks)}
                />
              ) : (
                <div className="agent-guideline-meta">
                  {p.approved ? (
                    <>
                      <button
                        type="button"
                        className="btn btn-sm btn-ghost"
                        aria-label={`撤销批准 ${p.name}`}
                        disabled={busyName === p.name}
                        onClick={() => void onUnapprove(p)}
                      >
                        撤销批准
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-ghost"
                        aria-label={`修改分项 ${p.name}`}
                        disabled={busyName === p.name}
                        onClick={() => setEditing(p.name)}
                      >
                        修改分项
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        type="button"
                        className="btn btn-sm btn-ghost"
                        aria-label={`整包批准 ${p.name}`}
                        disabled={busyName === p.name}
                        onClick={() => void onBundle(p)}
                      >
                        整包批准
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-ghost"
                        aria-label={`自定义批准 ${p.name}`}
                        disabled={busyName === p.name}
                        onClick={() => setEditing(p.name)}
                      >
                        自定义批准
                      </button>
                    </>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
