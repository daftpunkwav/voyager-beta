import { useEffect, useState } from 'react';
import { callCapability, uploadFile } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import type { PluginApproveResult, PluginInstallResult, PluginItem } from './types';

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

/** 插件(§9.13):发现 plugins/ 下的清单;整包或分项批准后其 skill/hook 即装,MCP 只登记待批准条目。
 *  phase-77:提供 zip(经 /api/uploads 运输)与本机目录两个安装入口,装完未批准、可立即批准;
 *  未批准插件可删除目录(已批准须先撤销)。 */
export function PluginsBlock() {
  const addToast = useUIStore((s) => s.addToast);
  const [plugins, setPlugins] = useState<PluginItem[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busyName, setBusyName] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null); // 正在分项勾选的插件名
  // 安装向导(phase-77):zip 文件 / 目录路径 / 覆盖开关;zipKey 用于装完清空文件框
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [zipKey, setZipKey] = useState(0);
  const [dirPath, setDirPath] = useState('');
  const [overwrite, setOverwrite] = useState(false);
  const [installing, setInstalling] = useState(false); // busy 态防双提交

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

  const onInstall = async () => {
    if (installing || (!zipFile && !dirPath.trim())) return;
    if (overwrite && !window.confirm('覆盖安装将先删除同名插件目录再装入新内容，确定覆盖？')) return;
    setInstalling(true);
    try {
      // zip 走既有上传运输(/api/uploads → workspace/imports),回传服务端路径;
      // 目录则直接传用户粘贴的绝对路径,来源合法性由后端按允许根校验
      const args = zipFile
        ? { zip_path: (await uploadFile(zipFile)).file_path, overwrite }
        : { source_dir: dirPath.trim(), overwrite };
      const res = await callCapability<PluginInstallResult>('agent', 'install_plugin', args);
      addToast({
        type: 'success',
        message: `已安装插件「${res.name}」${res.version ? ` v${res.version}` : ''}，尚未批准；在下方批准后才会装载`,
      });
      setZipFile(null);
      setZipKey((k) => k + 1); // 重挂载文件框,清掉已安装的文件名
      setDirPath('');
      setOverwrite(false);
      await reload();
    } catch (err) {
      addToast({ type: 'error', message: `安装失败：${extractErrorMessage(err)}` });
    } finally {
      setInstalling(false);
    }
  };

  const onDelete = async (p: PluginItem) => {
    if (!window.confirm(`删除插件「${p.name}」（目录 ${p.path}）？该操作不可恢复。`)) return;
    setBusyName(p.name);
    try {
      await callCapability('agent', 'uninstall_plugin', { name: p.name });
      addToast({ type: 'success', message: `已删除插件「${p.name}」` });
      await reload();
    } catch (err) {
      addToast({ type: 'error', message: `删除失败：${extractErrorMessage(err)}` });
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
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <input
            type="file"
            accept=".zip"
            aria-label="选择 zip 安装包"
            key={zipKey}
            disabled={installing}
            onChange={(e) => setZipFile(e.target.files?.[0] ?? null)}
            style={{ fontSize: 12 }}
          />
          <input
            type="text"
            aria-label="插件目录路径"
            placeholder="或粘贴本机插件目录的绝对路径（须在工作目录或附加根内）"
            value={dirPath}
            disabled={installing}
            onChange={(e) => setDirPath(e.target.value)}
            style={{ flex: 1, minWidth: 220, fontSize: 12 }}
          />
        </div>
        <div
          style={{
            display: 'flex', alignItems: 'center', gap: 12, marginTop: 6, flexWrap: 'wrap',
          }}
        >
          <label
            className="plugin-picker-option"
            style={{ fontSize: 12, margin: 0 }}
          >
            <input
              type="checkbox"
              aria-label="覆盖同名插件"
              checked={overwrite}
              disabled={installing}
              onChange={(e) => setOverwrite(e.target.checked)}
            />
            覆盖同名插件
          </label>
          <span className="muted" style={{ fontSize: 11 }}>
            同名默认拒绝覆盖；已批准的同名插件不会被覆盖，须先撤销批准。
          </span>
          <button
            type="button"
            className="btn btn-sm btn-primary"
            aria-label="安装插件"
            disabled={installing || (!zipFile && !dirPath.trim())}
            onClick={() => void onInstall()}
          >
            {installing ? '安装中…' : '安装插件'}
          </button>
        </div>
      </div>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>读取失败请刷新。</p>
      ) : plugins === null ? (
        <p className="muted" style={{ fontSize: 12 }}>插件清单加载中…</p>
      ) : plugins.length === 0 ? (
        <p className="muted" style={{ fontSize: 12 }}>
          还没有发现插件。把含 plugin.json 的插件目录放进仓库根的 plugins/ 下即可出现在这里，
          也可以用上方安装入口从 zip 或本机目录安装。
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
                      <button
                        type="button"
                        className="btn btn-sm btn-ghost"
                        aria-label={`删除插件 ${p.name}`}
                        disabled={busyName === p.name}
                        onClick={() => void onDelete(p)}
                      >
                        删除
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
