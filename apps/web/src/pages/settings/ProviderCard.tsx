/** 提供商卡片:元信息 + 启用开关 + 默认模型 + key 配置 + 测连接 + 删除。 */

import { useState } from 'react';
import { callCapability, ServiceError } from '@/bridge/client';
import type { Provider } from './ProviderSection';

interface CardProps {
  provider: Provider;
  onChanged: () => Promise<void> | void;
}

export function ProviderCard({ provider: p, onChanged }: CardProps) {
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [keyInput, setKeyInput] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(false);

  const run = async (tag: string, fn: () => Promise<string>) => {
    setBusy(tag);
    setMessage(null);
    try {
      setMessage({ ok: true, text: await fn() });
    } catch (err) {
      const e = err as ServiceError;
      setMessage({ ok: false, text: e.hint ? `${e.message}(${e.hint})` : e.message });
    } finally {
      setBusy(null);
    }
  };

  const toggleEnabled = () =>
    run('toggle', async () => {
      await callCapability('llm', 'update_provider', {
        provider_id: p.id,
        enabled: !p.enabled,
      });
      await onChanged();
      return p.enabled ? '已停用' : '已启用';
    });

  const setDefaultModel = (model: string) =>
    run('model', async () => {
      await callCapability('llm', 'update_provider', {
        provider_id: p.id,
        default_model: model,
      });
      await onChanged();
      return `默认模型已改为 ${model}`;
    });

  const saveKey = () =>
    run('key', async () => {
      if (!keyInput) return '未输入 key';
      await callCapability('llm', 'set_api_key', {
        provider_id: p.id,
        api_key: keyInput,
      });
      setKeyInput('');
      await onChanged();
      return 'api key 已保存';
    });

  const testConnection = () =>
    run('test', async () => {
      const out = await callCapability<{ ok: boolean; latency_ms: number; error: string }>(
        'llm',
        'test_connection',
        { provider_id: p.id },
      );
      if (!out.ok) return `失败:${out.error}`;
      return `连通正常,延迟 ${out.latency_ms}ms`;
    });

  const remove = () =>
    run('remove', async () => {
      await callCapability('llm', 'remove_provider', { provider_id: p.id });
      await onChanged();
      return '已删除';
    });

  return (
    <div className="provider-card">
      <div className="provider-card__head">
        <span className="provider-card__name">{p.display_name}</span>
        <span className={`setting-badge ${p.has_api_key ? 'setting-badge--ok' : 'setting-badge--none'}`}>
          {p.has_api_key ? 'key 已配置' : '未配置 key'}
        </span>
        {!p.enabled ? <span className="setting-badge setting-badge--none">已停用</span> : null}
        <span className="provider-card__meta">
          {p.api_format} · {p.base_url}
        </span>
      </div>
      <div className="provider-card__actions">
        <label className="small muted">
          默认模型
          <select
            className="setting-input"
            style={{ width: 'auto', marginLeft: 6 }}
            value={p.default_model}
            disabled={busy !== null}
            onChange={(e) => void setDefaultModel(e.target.value)}
          >
            {p.models.length === 0 ? <option value="">(无模型,先编辑)</option> : null}
            {p.models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="btn" disabled={busy !== null} onClick={toggleEnabled}>
          {p.enabled ? '停用' : '启用'}
        </button>
        <button type="button" className="btn" disabled={busy !== null} onClick={testConnection}>
          {busy === 'test' ? '测试中…' : '测试连接'}
        </button>
        <input
          className="setting-input"
          style={{ width: 180 }}
          type="password"
          placeholder={p.has_api_key ? '输入以覆盖 key' : '输入 api key'}
          autoComplete="off"
          value={keyInput}
          disabled={busy !== null}
          onChange={(e) => setKeyInput(e.target.value)}
        />
        <button type="button" className="btn" disabled={busy !== null || !keyInput} onClick={saveKey}>
          保存 key
        </button>
        {confirmDelete ? (
          <>
            <button type="button" className="btn" disabled={busy !== null} onClick={remove}>
              确认删除
            </button>
            <button type="button" className="btn" onClick={() => setConfirmDelete(false)}>
              取消
            </button>
          </>
        ) : (
          <button
            type="button"
            className="btn"
            disabled={busy !== null}
            onClick={() => setConfirmDelete(true)}
          >
            删除
          </button>
        )}
      </div>
      {message ? (
        <div className={`small ${message.ok ? '' : 'setting-field__error'}`}>{message.text}</div>
      ) : null}
    </div>
  );
}
