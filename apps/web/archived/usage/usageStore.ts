/** 用量页状态:时间窗(7/30/90)切换 + llm.get_usage_stats 聚合数据。 */

import { create } from 'zustand';
import { callCapability, ServiceError } from '@/bridge/client';

export interface ModelUsage {
  model: string;
  input: number;
  output: number;
  calls: number;
}

export interface UsageStats {
  days: number;
  input_tokens: number;
  output_tokens: number;
  calls: number;
  by_model: ModelUsage[];
}

export type UsageWindow = 7 | 30 | 90;

interface UsageState {
  days: UsageWindow;
  stats: UsageStats | null;
  loading: boolean;
  error: { code: string; message: string } | null;
  init: () => Promise<void>;
  setDays: (days: UsageWindow) => void;
}

export const useUsageStore = create<UsageState>((set, get) => ({
  days: 30,
  stats: null,
  loading: false,
  error: null,

  init: async () => {
    set({ loading: true, error: null });
    try {
      const stats = await callCapability<UsageStats>('llm', 'get_usage_stats', {
        days: get().days,
      });
      set({ stats, loading: false });
    } catch (err) {
      const e = err as ServiceError;
      set({ loading: false, error: { code: e.code, message: e.message } });
    }
  },

  setDays: (days) => {
    set({ days });
    void get().init();
  },
}));
