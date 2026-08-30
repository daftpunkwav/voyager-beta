/** 新增提供商:预设来自 llm.list_builtin_providers(后端目录为真相),
 *  经 llm.add_provider 入库;key 不在此填,添加后在详情卡片配置。 */

import { useEffect, useState } from 'react';
import { callCapability, ServiceError } from '@/bridge/client';
import type { LlmApiFormat } from '@/api/types';
import { LLM_API_FORMAT_OPTIONS } from '@/constants/llmConfig';

interface BuiltinPreset {
  preset_id: string;
  display_name: string;
  base_url: string;
  api_format: LlmApiFormat;
  models: string[];
}

interface LlmProviderAddProps {
  /** 保存成功后回调,携带新提供商 id(空串 = 仅刷新列表) */
  onDone: (id: string) => void | Promise<void>;
}

export function LlmProviderAdd({ onDone }: LlmProviderAddProps) {
  const [presets, setPresets] = useState<BuiltinPreset[]>([]);
  const [presetId, setPresetId] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [apiFormat, setApiFormat] = useState<LlmApiFormat>('chat');
  const [modelsText, setModelsText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    callCapability<BuiltinPreset[]>('llm', 'list_builtin_providers')
      .then(setPresets)
      .catch((err) => setError((err as ServiceError).message));
  }, []);

  const applyPreset = (preset: BuiltinPreset | undefined) => {
    setPresetId(preset?.preset_id ?? '');
    setDisplayName(preset?.display_name ?? '');
    setBaseUrl(preset?.base_url ?? '');
    setApiFormat(preset?.api_format ?? 'chat');
    setModelsText((preset?.models ?? []).join(', '));
  };

  const submit = async () => {
    setSaving(true);
    setError(null);
    try {
      const created = await callCapability<{ id: string }>('llm', 'add_provider', {
        display_name: displayName.trim() || '未命名提供商',
        base_url: baseUrl.trim(),
        api_format: apiFormat,
        models: modelsText
          .split(/[,，\n]/)
          .map((m) => m.trim())
          .filter(Boolean),
        preset_id: presetId,
      });
      await onDone(created?.id ?? '');
    } catch (err) {
      const e = err as ServiceError;
      setError(e.hint ? `${e.message}(${e.hint})` : e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      className="provider-editor glass-card glass-card--overview-inner"
      style={{ marginBottom: 16 }}
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <div className="form-row">
        <label htmlFor="llm-add-preset">从内置目录添加</label>
        <select
          id="llm-add-preset"
          className="field input"
          value={presetId}
          onChange={(e) =>
            applyPreset(presets.find((p) => e.target.value === p.preset_id))
          }
        >
          <option value="">自定义</option>
          {presets.map((p) => (
            <option key={p.preset_id} value={p.preset_id}>
              {p.display_name}
            </option>
          ))}
        </select>
      </div>
      <div className="form-row">
        <label htmlFor="llm-add-name">显示名称</label>
        <input
          id="llm-add-name"
          className="field input"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
        />
      </div>
      <div className="form-row">
        <label htmlFor="llm-add-url">Base URL</label>
        <input
          id="llm-add-url"
          className="field input"
          value={baseUrl}
          placeholder="https://api.example.com/v1"
          onChange={(e) => setBaseUrl(e.target.value)}
        />
      </div>
      <div className="form-row">
        <label htmlFor="llm-add-format">API 格式</label>
        <select
          id="llm-add-format"
          className="field input"
          value={apiFormat}
          onChange={(e) => setApiFormat(e.target.value as LlmApiFormat)}
        >
          {LLM_API_FORMAT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}({opt.hint})
            </option>
          ))}
        </select>
      </div>
      <div className="form-row">
        <label htmlFor="llm-add-models">可用模型(逗号或换行分隔)</label>
        <textarea
          id="llm-add-models"
          className="field input"
          rows={2}
          value={modelsText}
          onChange={(e) => setModelsText(e.target.value)}
        />
      </div>
      {error ? <div className="setting-field__error small">{error}</div> : null}
      <div className="settings-actions llm-actions">
        <button type="submit" className="btn btn-primary" disabled={saving || !baseUrl.trim()}>
          {saving ? '保存中…' : '保存(api key 稍后在卡片上配置)'}
        </button>
      </div>
    </form>
  );
}
