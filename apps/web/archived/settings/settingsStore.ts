/** 设置页状态:schema 缓存 + 写入(脏值在控件本地,提交成功后回写缓存)。 */

import { create } from 'zustand';
import { callCapability } from '@/bridge/client';

export interface SettingItem {
  key: string;
  module: string;
  type: 'str' | 'int' | 'float' | 'bool' | 'choice' | 'json';
  description: string;
  secret: boolean;
  choices: string[];
  min: number | null;
  max: number | null;
  has_value: boolean;
  default?: unknown;
  value?: unknown;
}

interface SettingsState {
  items: SettingItem[];
  loading: boolean;
  error: string | null;
  load: () => Promise<void>;
  /** 写单项;成功后把返回的 schema 行回写缓存(secret 项仍只有 has_value)。 */
  setValue: (key: string, value: unknown) => Promise<void>;
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  items: [],
  loading: false,
  error: null,

  load: async () => {
    set({ loading: true, error: null });
    try {
      const items = await callCapability<SettingItem[]>('settings', 'get_settings');
      set({ items, loading: false });
    } catch (err) {
      const e = err as { message?: string };
      set({ loading: false, error: e.message ?? '加载设置失败' });
    }
  },

  setValue: async (key, value) => {
    const updated = await callCapability<SettingItem>('settings', 'set_setting', {
      key,
      value,
    });
    set({
      items: get().items.map((it) => (it.key === key ? { ...it, ...updated } : it)),
    });
  },
}));

/** 分组显示名(module 即分组键,未见过的分组回退原词)。 */
export const MODULE_LABELS: Record<string, string> = {
  appearance: '外观',
  privacy: '隐私',
  gateway: '网关',
  notes: '笔记',
  graph: '图谱',
  sources: '资源库',
  llm: '模型',
  agent: 'Agent',
};

export function moduleLabel(module: string): string {
  return MODULE_LABELS[module] ?? module;
}
