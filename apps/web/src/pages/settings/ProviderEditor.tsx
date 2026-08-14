/** 提供商新增表单:内置目录选择 → 预填默认值;add_provider 无 key 字段(key 在卡片配)。 */

import { useEffect, useState } from 'react';
import { callCapability, ServiceError } from '@/bridge/client';

interface EditorProps {
  onDone: () => void;
}

interface Preset {
  preset_id: string;
  display_name: string;
  base_url: string;
  api_format: 'chat' | 'anthropic';
  models: string[];
}

export function ProviderEditor({ onDone }: EditorProps) {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [presetId, setPresetId] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [apiFormat, setApiFormat] = useState<'chat' | 'anthropic'>('chat');
  const [modelsText, setModelsText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    callCapability<Preset[]>('llm', 'list_builtin_providers')
      .then((list) => {
        setPresets(list);
        const first = list[0];
        if (first) applyPreset(first);
      })
      .catch((err) => setError((err as ServiceError).message));
  }, []);

  const applyPreset = (preset: Preset | undefined) => {
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
      await callCapability('llm', 'add_provider', {
        display_name: displayName.trim() || '未命名提供商',
        base_url: baseUrl.trim(),
        api_format: apiFormat,
        models: modelsText
          .split(/[,，\n]/)
          .map((m) => m.trim())
          .filter(Boolean),
        preset_id: presetId,
      });
      onDone();
    } catch (err) {
      setError((err as ServiceError).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      className="provider-editor"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <label>
        内置目录
        <select
          className="setting-input"
          value={presetId}
          onChange={(e) => {
            applyPreset(presets.find((p) => e.target.value === p.preset_id));
            if (!e.target.value) {
              // 自定义:清空预填,留用户填写
            }
          }}
        >
          <option value="">自定义</option>
          {presets.map((p) => (
            <option key={p.preset_id} value={p.preset_id}>
              {p.display_name}
            </option>
          ))}
        </select>
      </label>
      <label>
        名称
        <input
          className="setting-input"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
        />
      </label>
      <label>
        API 地址
        <input
          className="setting-input"
          value={baseUrl}
          placeholder="https://api.example.com/v1"
          onChange={(e) => setBaseUrl(e.target.value)}
        />
      </label>
      <label>
        API 格式
        <select
          className="setting-input"
          value={apiFormat}
          onChange={(e) => setApiFormat(e.target.value as 'chat' | 'anthropic')}
        >
          <option value="chat">chat(OpenAI 兼容)</option>
          <option value="anthropic">anthropic</option>
        </select>
      </label>
      <label>
        可用模型(逗号分隔)
        <textarea
          className="setting-input"
          rows={2}
          value={modelsText}
          onChange={(e) => setModelsText(e.target.value)}
        />
      </label>
      {error ? <div className="setting-field__error small">{error}</div> : null}
      <div className="provider-card__actions">
        <button type="submit" className="btn btn-primary" disabled={saving || !baseUrl.trim()}>
          {saving ? '保存中…' : '保存(api key 稍后在卡片上配置)'}
        </button>
      </div>
    </form>
  );
}
