import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import type { LlmProviderConfig, Settings } from '@/api/types';
import type { LlmTestResult } from '@/stores/settingsStore';
import { createProviderFromPreset } from '@/constants/llmConfig';
import { LlmAgentOverrides } from './llm/LlmAgentOverrides';
import { LlmProviderDetail } from './llm/LlmProviderDetail';
import { LlmProviderList } from './llm/LlmProviderList';

interface LlmSettingsSectionProps {
  settings: Settings;
  updateSettings: (data: Partial<Settings>) => Promise<unknown>;
  testLLM: (model?: string, providerId?: string) => Promise<unknown>;
  isTestingLLM: boolean;
  testResult: LlmTestResult | null;
  onSaveApiKey: (key: string, providerId?: string) => Promise<unknown>;
}

function ensureProviders(settings: Settings): LlmProviderConfig[] {
  if (settings.llm_providers?.length) return settings.llm_providers;
  // 兼容旧扁平配置
  return [
    {
      id: settings.llm_default_provider_id || 'legacy-default',
      preset_id: settings.llm_provider || 'custom',
      display_name: settings.llm_provider_display_name || '默认供应商',
      enabled: true,
      api_base: settings.llm_api_base,
      api_format: settings.llm_api_format,
      available_models: settings.llm_available_models ?? [],
      default_model: settings.llm_default_model || settings.llm_model,
      configured: settings.llm_configured,
      api_key_masked: settings.llm_api_key_masked,
    },
  ];
}

export function LlmSettingsSection({
  settings,
  updateSettings,
  testLLM,
  isTestingLLM,
  testResult,
  onSaveApiKey,
}: LlmSettingsSectionProps) {
  const providers = useMemo(() => ensureProviders(settings), [settings]);
  const [selectedId, setSelectedId] = useState<string | null>(
    settings.llm_default_provider_id || providers[0]?.id || null,
  );

  useEffect(() => {
    if (!providers.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !providers.some((p) => p.id === selectedId)) {
      setSelectedId(settings.llm_default_provider_id || providers[0]?.id || null);
    }
  }, [providers, selectedId, settings.llm_default_provider_id]);

  const selected = providers.find((p) => p.id === selectedId) ?? providers[0];

  const persistProviders = async (
    next: LlmProviderConfig[],
    defaultId?: string | null,
  ) => {
    await updateSettings({
      llm_providers: next,
      llm_default_provider_id:
        defaultId === undefined ? settings.llm_default_provider_id : defaultId,
    });
  };

  const patchSelected = async (
    patch: Partial<LlmProviderConfig> & { api_key?: string },
  ) => {
    if (!selected) return;
    const { api_key: _k, ...rest } = patch;
    const next = providers.map((p) =>
      p.id === selected.id ? { ...p, ...rest } : p,
    );
    await persistProviders(next);
  };

  const addProvider = async () => {
    const draft = createProviderFromPreset('custom');
    const next = [...providers, draft];
    await persistProviders(
      next,
      settings.llm_default_provider_id || draft.id,
    );
    setSelectedId(draft.id);
  };

  const deleteProvider = async () => {
    if (!selected || providers.length <= 1) return;
    const next = providers.filter((p) => p.id !== selected.id);
    let defaultId = settings.llm_default_provider_id;
    if (defaultId === selected.id) defaultId = next[0]?.id ?? null;
    await persistProviders(next, defaultId);
    setSelectedId(next[0]?.id ?? null);
  };

  const anyConfigured =
    settings.llm_configured || providers.some((p) => p.configured);

  return (
    <div className="llm-settings">
      {!anyConfigured && (
        <div className="alert alert-warning">
          <strong>未配置</strong> — 请为至少一个供应商填写 API Key 并测试；未配置时
          Agent 将使用规则降级模式。
        </div>
      )}

      <p className="section-desc" style={{ marginTop: 0 }}>
        多供应商可并存；Agent 可单独指定供应商与模型。
        <Link to="/usage" style={{ marginLeft: 8 }}>
          查看 LLM 用量 →
        </Link>
      </p>

      <div className="llm-multi-layout">
        <LlmProviderList
          providers={providers}
          selectedId={selected?.id ?? null}
          defaultProviderId={settings.llm_default_provider_id}
          onSelect={setSelectedId}
          onAdd={() => void addProvider()}
        />
        {selected ? (
          <LlmProviderDetail
            provider={selected}
            isDefault={selected.id === settings.llm_default_provider_id}
            isTesting={isTestingLLM}
            testResult={testResult}
            onPatch={(patch) => void patchSelected(patch)}
            onSetDefault={() =>
              void updateSettings({ llm_default_provider_id: selected.id })
            }
            onDelete={() => void deleteProvider()}
            onSaveKey={async (key) => {
              await onSaveApiKey(key, selected.id);
            }}
            onTest={async (model) => {
              await testLLM(model, selected.id);
            }}
          />
        ) : (
          <div className="glass-card glass-card--overview-inner" style={{ padding: 24 }}>
            请添加供应商
          </div>
        )}
      </div>

      <LlmAgentOverrides
        settings={settings}
        providers={providers}
        updateSettings={updateSettings}
      />
    </div>
  );
}
