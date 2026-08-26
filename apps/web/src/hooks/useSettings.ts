import { useEffect } from 'react';
import { useSettingsStore } from '@/stores/settingsStore';

/** LLM 配置（供应商 / 模型 / 风格 / 探测） */
export function useSettings() {
  const settings = useSettingsStore((s) => s.settings);
  const isLoading = useSettingsStore((s) => s.isLoading);
  const loadSettings = useSettingsStore((s) => s.loadSettings);
  const updateSettings = useSettingsStore((s) => s.updateSettings);
  const saveLlmApiKey = useSettingsStore((s) => s.saveLlmApiKey);
  const testLLM = useSettingsStore((s) => s.testLLM);
  const isTestingLLM = useSettingsStore((s) => s.isTestingLLM);
  const testResult = useSettingsStore((s) => s.testResult);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  return {
    settings,
    isLoading,
    loadSettings,
    updateSettings,
    saveLlmApiKey,
    testLLM,
    isTestingLLM,
    testResult,
  };
}
