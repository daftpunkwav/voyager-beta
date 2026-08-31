import { useState } from 'react';
import { callCapability } from '@/bridge/client';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import type { McpApproveResult, McpServerState } from './types';

interface McpListProps {
  servers: McpServerState[];
  onChange: () => void;
}

/** 外接 MCP 列表:预览、批准、刷新、移除 */
export function McpList({ servers, onChange }: McpListProps) {
  const addToast = useUIStore((s) => s.addToast);
  const [checked, setChecked] = useState<Record<string, string[]>>({});
  const [confirmRemoveId, setConfirmRemoveId] = useState<string | null>(null);

  const refreshPreview = async (id: string) => {
    try {
      await callCapability('agent', 'preview_mcp_tools', { id });
      onChange();
    } catch (err) {
      addToast({ type: 'error', message: `刷新工具列表失败：${extractErrorMessage(err)}` });
    }
  };

  const approve = async (id: string, names: string[]) => {
    try {
      const res = await callCapability<McpApproveResult>('agent', 'approve_mcp_tools', { id, names });
      addToast({
        type: 'success',
        message: `已批准 ${res.mounted.length} 个工具进名册；当前这句对话若已开始，下一句或新对话可见`,
      });
      onChange();
    } catch (err) {
      addToast({ type: 'error', message: `批准失败：${extractErrorMessage(err)}` });
    }
  };

  const toggleTool = (sid: string, tool: string) => {
    setChecked((prev) => {
      const cur = prev[sid] ?? [];
      return {
        ...prev,
        [sid]: cur.includes(tool) ? cur.filter((t) => t !== tool) : [...cur, tool],
      };
    });
  };

  const remove = async (id: string) => {
    try {
      await callCapability('agent', 'remove_mcp_server', { id });
      addToast({ type: 'success', message: `已移除 MCP「${id}」，其工具已从名册卸下` });
    } catch (err) {
      addToast({ type: 'error', message: `移除失败：${extractErrorMessage(err)}` });
    } finally {
      setConfirmRemoveId(null);
      onChange();
    }
  };

  return (
    <>
      <ul className="memory-entry-list">
        {servers.map((s) => (
          <li key={s.id} className="memory-entry">
            <span className="memory-kind">{s.name}</span>
            <span className="memory-entry-summary">
              {s.kind === 'stdio' ? `stdio · ${s.command}` : s.url}
              {' · '}
              {s.approved.includes('*')
                ? '已批准（整包）'
                : s.approved.length > 0
                  ? `已批准 ${s.approved.length} 项`
                  : '未批准'}
              {s.connected ? '' : ' · 未连接'}
            </span>
            {s.error && (
              <span className="memory-entry-summary" style={{ color: 'var(--error)' }}>
                {s.error}
              </span>
            )}
            {s.mounted.length > 0 && (
              <span className="muted" style={{ fontSize: 12 }}>
                已挂载 {s.mounted.length} 个工具（mcp__{s.id}__…）
              </span>
            )}
            {!s.approved.includes('*') && s.connected && s.preview.length > 0 && (
              <div style={{ margin: '6px 0' }}>
                {s.preview.map((t) => (
                  <div key={t.name} style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                    {s.approval === 'item' && (
                      <input
                        type="checkbox"
                        checked={(checked[s.id] ?? []).includes(t.name)}
                        onChange={() => toggleTool(s.id, t.name)}
                        aria-label={`${s.id} · ${t.name}`}
                      />
                    )}
                    <span style={{ fontSize: 12 }}>
                      <strong>{t.name}</strong>
                      {t.description ? ` — ${t.description}` : ''}
                    </span>
                  </div>
                ))}
                <div className="agent-guideline-meta">
                  {s.approval === 'package' ? (
                    <button
                      type="button"
                      className="btn btn-sm btn-ghost"
                      aria-label={`批准全部 ${s.name}`}
                      onClick={() => void approve(s.id, ['*'])}
                    >
                      批准全部
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-sm btn-ghost"
                      aria-label={`批准所选 ${s.name}`}
                      disabled={(checked[s.id]?.length ?? 0) === 0}
                      onClick={() => void approve(s.id, checked[s.id] ?? [])}
                    >
                      批准所选
                    </button>
                  )}
                </div>
              </div>
            )}
            <div className="agent-guideline-meta">
              <button
                type="button"
                className="btn btn-sm btn-ghost"
                aria-label={`刷新工具列表 ${s.name}`}
                onClick={() => void refreshPreview(s.id)}
              >
                刷新工具列表
              </button>
              <button
                type="button"
                className="btn btn-sm btn-danger"
                aria-label={`移除 ${s.name}`}
                onClick={() => setConfirmRemoveId(s.id)}
              >
                移除
              </button>
            </div>
          </li>
        ))}
      </ul>

      {confirmRemoveId && (
        <ConfirmDialog
          open
          title={`移除 MCP「${confirmRemoveId}」`}
          message="会断开连接、从工具名册卸下它的工具并删除配置。确定移除？"
          confirmLabel="移除"
          danger
          onConfirm={() => void remove(confirmRemoveId)}
          onCancel={() => setConfirmRemoveId(null)}
        />
      )}
    </>
  );
}
