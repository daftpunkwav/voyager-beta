import { useEffect, useState } from 'react';
import type { LlmApiFormat, LlmProvider } from '@/api/types';
import type { LlmTestOutcome } from '@/components/settings/LlmSettingsSection';
import { GlassSelect } from '@/components/common/GlassSelect';
import { LLM_API_FORMAT_OPTIONS } from '@/constants/llmConfig';
import { GLASS_INNER } from '@/constants/glassTokens';

interface LlmProviderDetailProps {
  provider: LlmProvider;
  isDefault: boolean;
  isTesting: boolean;
  testResult: LlmTestOutcome | null;
  onPatch: (
    patch: Partial<Pick<LlmProvider, 'display_name' | 'base_url' | 'api_format' | 'models' | 'default_model' | 'enabled'>>,
  ) => Promise<unknown>;
  onSaveKey: (key: string) => Promise<unknown>;
  onSetDefault: () => void;
  onDelete: () => void;
  onTest: (model: string) => void;
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
  onSaveKey,
  onSetDefault,
  onDelete,
  onTest,
}: LlmProviderDetailProps) {
  const [nameDraft, setNameDraft] = useState(provider.display_name);
  const [urlDraft, setUrlDraft] = useState(provider.base_url);
  const [apiKeyDraft, setApiKeyDraft] = useState('');
  const [newModel, setNewModel] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);

  // 外部 reload 回来的值同步进本地草稿(切换提供商或远端变更后)
  useEffect(() => {
    setNameDraft(provider.display_name);
  }, [provider.id, provider.display_name]);
  useEffect(() => {
    setUrlDraft(provider.base_url);
  }, [provider.id, provider.base_url]);

  const run = (fn: () => Promise<unknown>) => {
    setActionError(null);
    fn().catch((err) => {
      const e = err as { message?: string; hint?: string };
      setActionError(e.hint ? `${e.message}(${e.hint})` : e.message ?? '操作失败');
    });
  };

  const commitName = () => {
    const name = nameDraft.trim();
    if (!name || name === provider.display_name) return;
    run(() => onPatch({ display_name: name }));
  };

  const commitBaseUrl = () => {
    const url = urlDraft.trim();
    if (!url || url === provider.base_url) return;
    run(() => onPatch({ base_url: url }));
  };

  const addModel = () => {
    const name = newModel.trim();
    if (!name || provider.models.includes(name)) return;
    setNewModel('');
    run(() => onPatch({ models: [...provider.models, name] }));
  };

  const removeModel = (model: string) => {
    const next = provider.models.filter((m) => m !== model);
    const patch: Parameters<typeof onPatch>[0] = { models: next };
    if (provider.default_model === model) {
      patch.default_model = next[0] ?? '';
    }
    run(() => onPatch(patch));
  };

  const saveKey = () => {
    const key = apiKeyDraft.trim();
    if (!key) return;
    setApiKeyDraft('');
    run(() => onSaveKey(key));
  };

  const activeModel = provider.default_model || provider.models[0] || '';

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
            onClick={() => !provider.enabled && run(() => onPatch({ enabled: true }))}
          >
            已启用
          </button>
          <button
            type="button"
            className={`llm-enable-pill ${!provider.enabled ? 'is-off' : ''}`}
            onClick={() => provider.enabled && run(() => onPatch({ enabled: false }))}
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
        <label htmlFor="llm-display-name">显示名称</label>
        <input
          id="llm-display-name"
          className="field input"
          value={nameDraft}
          onChange={(e) => setNameDraft(e.target.value)}
          onBlur={commitName}
        />
      </div>

      <div className="form-row">
        <label htmlFor="llm-base-url">Base URL</label>
        <input
          id="llm-base-url"
          className="field input"
          value={urlDraft}
          onChange={(e) => setUrlDraft(e.target.value)}
          onBlur={commitBaseUrl}
          placeholder="https://…"
        />
      </div>

      <div className="form-row">
        <label>API 格式</label>
        <ul className={`llm-format-list ${GLASS_INNER}`}>
          {LLM_API_FORMAT_OPTIONS.map((opt) => {
            const selected = provider.api_format === opt.value;
            return (
              <li key={opt.value}>
                <button
                  type="button"
                  className={`llm-format-item ${selected ? 'is-selected' : ''}`}
                  onClick={() => !selected && run(() => onPatch({ api_format: opt.value as LlmApiFormat }))}
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
          <span className={`llm-key-masked ${provider.has_api_key ? '' : 'muted'}`}>
            {provider.has_api_key ? '（已保存,输入可覆盖）' : '（未配置）'}
          </span>
        </label>
        <div className="llm-key-row">
          <input
            id="llm-api-key"
            type="password"
            className="field input"
            placeholder={provider.has_api_key ? '输入以覆盖 key' : 'sk-… 或供应商密钥'}
            value={apiKeyDraft}
            onChange={(e) => setApiKeyDraft(e.target.value)}
            autoComplete="off"
          />
        </div>
        <div className="settings-actions llm-actions">
          <button
            type="button"
            className="btn btn-primary"
            disabled={!apiKeyDraft.trim()}
            onClick={saveKey}
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
          options={(provider.models.length
            ? provider.models
            : [provider.default_model].filter(Boolean)
          ).map((m) => ({ value: m, label: m }))}
          onChange={(v) => v !== provider.default_model && run(() => onPatch({ default_model: v }))}
          aria-label="默认模型"
        />
      </div>

      <div className="form-row">
        <label>模型列表</label>
        <ul className="llm-model-list">
          {provider.models.map((m) => (
            <li key={m} className={`llm-model-chip ${GLASS_INNER}`}>
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
          disabled={isTesting || !activeModel || !provider.has_api_key}
          onClick={() => onTest(activeModel)}
          data-testid="test-llm-btn"
          title={provider.has_api_key ? undefined : '先保存 api key 再测试'}
        >
          {isTesting
            ? `正在请求 ${activeModel}…`
            : `测试连接 · ${activeModel || '未选择'}`}
        </button>

        {testResult && (
          <div
            className={`llm-test-result ${testResult.ok ? 'llm-test-result--ok' : 'llm-test-result--fail'}`}
            role="status"
          >
            <div className="llm-test-result__head">
              <strong>{testResult.ok ? '✓ 连通正常' : '✗ 测试失败'}</strong>
              <span className="muted">
                {testResult.model ?? activeModel}
                {typeof testResult.latency_ms === 'number'
                  ? ` · ${formatLatency(testResult.latency_ms)}`
                  : ''}
              </span>
            </div>
            {!testResult.ok && (
              <pre className="llm-test-result__error">
                {testResult.error?.trim() || '未知错误'}
              </pre>
            )}
          </div>
        )}

        {actionError ? (
          <div className="setting-field__error small" role="alert">
            {actionError}
          </div>
        ) : null}
      </div>
    </div>
  );
}
