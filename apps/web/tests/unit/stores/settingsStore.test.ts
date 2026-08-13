import { beforeEach, describe, expect, it } from 'vitest';
import { useSettingsStore } from '@/stores/settingsStore';
import type { Settings } from '@/api/types';
import { createDefaultAgentLlmConfigs } from '@/constants/llmConfig';

const fakeSettings: Settings = {
  theme: 'light',
  font_scale: 1.0,
  code_font: 'JetBrains Mono',
  llm_provider: 'openai',
  llm_provider_display_name: 'OpenAI',
  llm_default_model: 'gpt-4o',
  llm_model: 'gpt-4o',
  llm_api_base: 'https://api.openai.com/v1',
  llm_api_format: 'openai',
  llm_available_models: ['gpt-4o', 'gpt-4o-mini'],
  llm_api_key_masked: 'sk-****a8d2',
  llm_configured: true,
  agent_llm_configs: createDefaultAgentLlmConfigs(),
};

describe('settingsStore (state shape only)', () => {
  beforeEach(() => {
    useSettingsStore.setState({
      settings: null,
      isLoading: false,
      isTestingLLM: false,
      testResult: null,
      error: null,
    });
  });

  it('initial state has no settings and no error', () => {
    const s = useSettingsStore.getState();
    expect(s.settings).toBeNull();
    expect(s.isLoading).toBe(false);
    expect(s.error).toBeNull();
  });

  it('testResult can be set and cleared via setState', () => {
    expect(useSettingsStore.getState().testResult).toBeNull();
    useSettingsStore.setState({ testResult: { success: true, latency_ms: 350 } });
    expect(useSettingsStore.getState().testResult).toEqual({ success: true, latency_ms: 350 });
  });

  it('error can be set', () => {
    useSettingsStore.setState({ error: 'boom' });
    expect(useSettingsStore.getState().error).toBe('boom');
  });

  it('fake settings payload has synced llm_model / llm_default_model', () => {
    // sanity: 后续真实测试应覆盖 updateSettings() 调用 getApi()；
    // 这里仅校验 fixture 构造正确。
    expect(fakeSettings.llm_model).toBe(fakeSettings.llm_default_model);
    expect(fakeSettings.agent_llm_configs.length).toBeGreaterThan(0);
  });
});