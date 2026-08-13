import { useState } from 'react';
import type { LlmProviderConfig } from '@/api/types';
import type { LlmTestResult } from '@/stores/settingsStore';
import { GlassSelect } from '@/components/common/GlassSelect';
import {
  findProviderPreset,
  LLM_API_FORMAT_OPTIONS,
  LLM_PROVIDER_PRESETS,
} from '@/constants/llmConfig';
import { OVERVIEW_INNER_GLASS } from '@/constants/overviewGlass';

interface LlmProviderDetailProps {
  provider: LlmProviderConfig;
  isDefault: boolean;
  isTesting: boolean;
  testResult: LlmTestResult | null;
  onPatch: (patch: Partial<LlmProviderConfig> & { api_key?: string }) => void;
  onSetDefault: () => void;
  onDelete: () => void;
  onSaveKey: (key: string) => Promise<void>;
  onTest: (model: string) => Promise<void>;
}

function formatLatency(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return '-';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const sec = ms / 1000;
  return `${sec.toFixed(sec >= 10 ? 1 : 2)} s`;
}

export function LlmProviderDetail({
  provider,
  isDefault,
  isTesting,
  testResult,
  onPatch,
  onSetDefault,
  onDelete,
  onSaveKey,
  onTest,
}: LlmProviderDetailProps) {
  const [apiKeyDraft, setApiKeyDraft] = useState('');
  const [newModel, setNewModel] = useState('');
  const [showKey, setShowKey] = useState(false);

  const applyPreset = (presetId: string) => {
    const preset = findProviderPreset(presetId);
    if (!preset) return;
    onPatch({
      preset_id: preset.id,
      display_name: preset.display_name,
      api_base: preset.default_base_url || null,
      api_format: preset.api_format,
      available_models: [...preset.available_models],
      default_model: preset.default_model,
    });
  };

  const addModel = () => {
    const name = newModel.trim();
    if (!name || provider.available_models.includes(name)) return;
    onPatch({ available_models: [...provider.available_models, name] });
    setNewModel('');
  };

  const removeModel = (model: string) => {
    const next = provider.available_models.filter((m) => m !== model);
    const default_model =
      provider.default_model === model ? (next[0] ?? '') : provider.default_model;
    onPatch({ available_models: next, default_model });
  };

  const activeModel = provider.default_model || provider.available_models[0] || '';

  return (
    <div className={`llm-provider-detail glass-card glass-card--overview-inner glass-overflow-visible`}>
      <div className="llm-provider-detail-head">
        <div className="llm-provider-detail-title-row">
          <h3 className="llm-block-title">{provider.display_name || '未命名供应商'}</h3>
          {!isDefault ? (
            <button type="button" className="btn btn-ghost btn-sm" onClick={onSetDefault}>
              设为默认
            </button>
          ) : (
            <span className="llm-provider-default-tag">默认</span>
          )}
        </div>
        <div className="llm-provider-enable-row">
          <button
            type="button"
            className={`llm-enable-pill ${provider.enabled ? 'is-on' : ''}`}
            onClick={() => onPatch({ enabled: true })}
          >
            已启用
          </button>
          <button
            type="button"
            className={`llm-enable-pill ${!provider.enabled ? 'is-off' : ''}`}
            onClick={() => onPatch({ enabled: false })}
          >
            禁用
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm llm-provider-delete"
            onClick={onDelete}
            aria-label="删除供应商"
          >
            删除
          </button>
        </div>
      </div>

      <div className="form-row">
        <label htmlFor="llm-preset">供应商预设</label>
        <GlassSelect
          id="llm-preset"
          value={provider.preset_id}
          options={LLM_PROVIDER_PRESETS.map((p) => ({
            value: p.id,
            label: p.display_name,
          }))}
          onChange={applyPreset}
          aria-label="供应商预设"
        />
      </div>

      <div className="form-row">
        <label htmlFor="llm-display-name">显示名称</label>
        <input
          id="llm-display-name"
          className="field input"
          value={provider.display_name}
          onChange={(e) => onPatch({ display_name: e.target.value })}
        />
      </div>

      <div className="form-row">
        <label htmlFor="llm-base-url">Base URL</label>
        <input
          id="llm-base-url"
          className="field input"
          value={provider.api_base ?? ''}
          onChange={(e) => onPatch({ api_base: e.target.value || null })}
          placeholder="https://…"
        />
      </div>

      <div className="form-row">
        <label>API 格式</label>
        <ul className={`llm-format-list ${OVERVIEW_INNER_GLASS}`}>
          {LLM_API_FORMAT_OPTIONS.map((opt) => {
            const selected = provider.api_format === opt.value;
            return (
              <li key={opt.value}>
                <button
                  type="button"
                  className={`llm-format-item ${selected ? 'is-selected' : ''}`}
                  onClick={() => onPatch({ api_format: opt.value })}
                >
                  <span>
                    {opt.label}
                    <span className="muted"> {opt.hint}</span>
                  </span>
                  {selected ? <span aria-hidden>✓</span> : null}
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="form-row">
        <label htmlFor="llm-api-key">
          API Key
          {provider.api_key_masked ? (
            <span className="llm-key-masked">（已保存 {provider.api_key_masked}）</span>
          ) : null}
        </label>
        <div className="llm-key-row">
          <input
            id="llm-api-key"
            type={showKey ? 'text' : 'password'}
            className="field input"
            placeholder="sk-… 或供应商密钥"
            value={apiKeyDraft}
            onChange={(e) => setApiKeyDraft(e.target.value)}
            autoComplete="off"
          />
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setShowKey((v) => !v)}
          >
            {showKey ? '隐藏' : '显示'}
          </button>
        </div>
        <div className="settings-actions llm-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              const key = apiKeyDraft.trim();
              if (!key) return;
              void (async () => {
                await onSaveKey(key);
                setApiKeyDraft('');
              })();
            }}
          >
            保存密钥
          </button>
        </div>
      </div>

      <div className="form-row">
        <label htmlFor="llm-default-model">默认模型</label>
        <GlassSelect
          id="llm-default-model"
          value={provider.default_model}
          options={(provider.available_models.length
            ? provider.available_models
            : [provider.default_model].filter(Boolean)
          ).map((m) => ({ value: m, label: m }))}
          onChange={(v) => onPatch({ default_model: v })}
          aria-label="默认模型"
        />
      </div>

      <div className="form-row">
        <label>模型列表</label>
        <ul className="llm-model-list">
          {provider.available_models.map((m) => (
            <li key={m} className={`llm-model-chip ${OVERVIEW_INNER_GLASS}`}>
              <span>{m}</span>
              {m === provider.default_model ? (
                <span className="llm-model-chip__default">默认</span>
              ) : null}
              <button type="button" aria-label={`移除 ${m}`} onClick={() => removeModel(m)}>
                ×
              </button>
            </li>
          ))}
        </ul>
        <div className="llm-model-add">
          <input
            className="field input"
            placeholder="添加模型 ID"
            value={newModel}
            onChange={(e) => setNewModel(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                addModel();
              }
            }}
          />
          <button type="button" className="btn btn-ghost btn-sm" onClick={addModel}>
            + 添加模型
          </button>
        </div>
      </div>

      <div className="llm-test-panel">
        <button
          type="button"
          className="btn btn-primary"
          disabled={isTesting || !provider.configured || !activeModel}
          onClick={() => void onTest(activeModel)}
          data-testid="test-llm-btn"
        >
          {isTesting
            ? `正在请求 ${activeModel}…`
            : `测试模型 · ${activeModel || '未选择'}`}
        </button>

        {testResult && (
          <div
            className={`llm-test-result ${testResult.success ? 'llm-test-result--ok' : 'llm-test-result--fail'}`}
            role="status"
          >
            <div className="llm-test-result__head">
              <strong>{testResult.success ? '✓ 测试通过' : '✗ 测试失败'}</strong>
              <span className="muted">
                {testResult.model ?? activeModel}
                {typeof testResult.latency_ms === 'number'
                  ? ` · ${formatLatency(testResult.latency_ms)}`
                  : ''}
              </span>
            </div>
            {testResult.success ? (
              <pre className="llm-test-result__reply">
                {testResult.reply?.trim() || '（无正文，但请求已成功）'}
              </pre>
            ) : (
              <pre className="llm-test-result__error">
                {testResult.error?.trim() || '未知错误'}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
