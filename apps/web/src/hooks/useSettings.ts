import { useEffect } from 'react';
import { useSettingsStore } from '@/stores/settingsStore';

/** 外观与 Agent 配置等 settings blob 项(供应商/key/测试已迁 llm.* 客户端,见 LlmSettingsSection) */
export function useSettings() {
  const settings = useSettingsStore((s) => s.settings);
  const isLoading = useSettingsStore((s) => s.isLoading);
  const loadSettings = useSettingsStore((s) => s.loadSettings);
  const updateSettings = useSettingsStore((s) => s.updateSettings);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  return {
    settings,
    isLoading,
    loadSettings,
    updateSettings,
  };
}
