import { useState } from 'react';
import { callCapability } from '@/bridge/client';
import { GlassSelect } from '@/components/common/GlassSelect';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { EMPTY_MCP_FORM } from './constants';
import type { McpAddResult, McpFormDraft } from './types';

interface McpFormProps {
  onAdded: () => void;
}

/** 外接 MCP 添加表单 */
export function McpForm({ onAdded }: McpFormProps) {
  const addToast = useUIStore((s) => s.addToast);
  const [form, setForm] = useState<McpFormDraft>(EMPTY_MCP_FORM);
  const [busy, setBusy] = useState(false);

  const handleAdd = async () => {
    const id = form.id.trim();
    if (!/^[a-z][a-z0-9-]{0,31}$/.test(id)) {
      addToast({ type: 'warning', message: 'id 须为小写字母开头的 1–32 位小写字母/数字/连字符' });
      return;
    }
    setBusy(true);
    try {
      const res = await callCapability<McpAddResult>('agent', 'add_mcp_server', {
        id,
        name: form.name.trim() || id,
        kind: form.kind,
        command: form.kind === 'stdio' ? form.command.trim() : '',
        args:
          form.kind === 'stdio'
            ? form.argsDraft.split('\n').map((s) => s.trim()).filter(Boolean)
            : [],
        url: form.kind === 'url' ? form.url.trim() : '',
        approval: form.approval,
      });
      setForm(EMPTY_MCP_FORM);
      if (res.connected) {
        addToast({
          type: 'success',
          message: `MCP「${id}」已添加并列出工具；批准后进入工具名册，下一句或新对话可见`,
        });
      } else {
        addToast({
          type: 'warning',
          message: `MCP「${id}」已保存，但连接失败：${res.error}。修好后可「刷新工具列表」`,
        });
      }
      onAdded();
    } catch (err) {
      addToast({ type: 'error', message: `添加 MCP 失败：${extractErrorMessage(err)}` });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="memory-subhead">添加外接 MCP</div>
      <div className="memory-form-row">
        <input
          className="field input"
          style={{ maxWidth: 160 }}
          placeholder="id（如 my-search）"
          value={form.id}
          onChange={(e) => setForm((f) => ({ ...f, id: e.target.value }))}
          aria-label="MCP id"
        />
        <input
          className="field input"
          style={{ maxWidth: 160 }}
          placeholder="展示名（可同 id）"
          value={form.name}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          aria-label="MCP 展示名"
        />
        <GlassSelect
          size="sm"
          value={form.kind}
          options={[
            { value: 'stdio', label: 'stdio 命令' },
            { value: 'url', label: 'HTTP URL' },
          ]}
          onChange={(v) => setForm((f) => ({ ...f, kind: v as McpFormDraft['kind'] }))}
          aria-label="MCP 类型"
        />
        <GlassSelect
          size="sm"
          value={form.approval}
          options={[
            { value: 'package', label: '整包批准' },
            { value: 'item', label: '逐项批准' },
          ]}
          onChange={(v) => setForm((f) => ({ ...f, approval: v as McpFormDraft['approval'] }))}
          aria-label="批准粒度"
        />
      </div>
      {form.kind === 'stdio' ? (
        <>
          <div className="memory-form-row">
            <input
              className="field input"
              placeholder="命令（如 npx / uv；Windows 上可能是 npx.cmd）"
              value={form.command}
              onChange={(e) => setForm((f) => ({ ...f, command: e.target.value }))}
              aria-label="MCP command"
            />
          </div>
          <textarea
            className="field input agent-guideline-textarea"
            rows={2}
            placeholder={'参数，一行一个\n如 -y\n如 @modelcontextprotocol/server-xxx'}
            value={form.argsDraft}
            onChange={(e) => setForm((f) => ({ ...f, argsDraft: e.target.value }))}
            aria-label="MCP args"
          />
        </>
      ) : (
        <div className="memory-form-row">
          <input
            className="field input"
            placeholder="https://…（MCP 端点 URL）"
            value={form.url}
            onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
            aria-label="MCP URL"
          />
        </div>
      )}
      <div className="agent-guideline-meta">
        <button
          type="button"
          className="btn btn-sm btn-primary"
          aria-label="添加 MCP"
          disabled={busy}
          onClick={() => void handleAdd()}
        >
          添加
        </button>
      </div>
    </>
  );
}
