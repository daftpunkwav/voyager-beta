import { create } from 'zustand';
import type { Settings } from '@/api/types';
import { getApi } from '@/api/client';
import { extractErrorMessage } from '@/utils/errors';

interface SettingsState {
  settings: Settings | null;
  isLoading: boolean;
  error: string | null;
  loadSettings: () => Promise<void>;
  updateSettings: (data: Partial<Settings>) => Promise<void>;
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  settings: null,
  isLoading: false,
  error: null,

  loadSettings: async () => {
    set({ isLoading: true, error: null });
    try {
      const api = getApi();
      const response = await api.getSettings();
      const data = response.data;
      set({
        settings: {
          ...data,
          agent_code_of_conduct: data.agent_code_of_conduct ?? '',
          agent_guidelines: data.agent_guidelines ?? [],
          llm_providers: data.llm_providers ?? [],
          llm_default_provider_id: data.llm_default_provider_id ?? null,
        },
        isLoading: false,
      });
    } catch (err) {
      set({ isLoading: false, error: extractErrorMessage(err) });
    }
  },

  updateSettings: async (data) => {
    const prev = get().settings;
    if (prev) {
      const optimistic = { ...prev, ...data };
      if (data.llm_default_model !== undefined) {
        optimistic.llm_model = data.llm_default_model;
      }
      set({ settings: optimistic });
    }
    try {
      const api = getApi();
      const response = await api.updateSettings(data);
      set({ settings: response.data });
    } catch (err) {
      if (prev) set({ settings: prev });
      set({ error: extractErrorMessage(err) });
      throw err;
    }
  },
}));
