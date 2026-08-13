/**
 * 本地学习者 store —— 无登录/注册；启动时拉取 /user/me。
 */
import { create } from 'zustand';
import type { User } from '@/api/types';
import { getApi } from '@/api/client';
import { clearLegacyTokenStorage } from '@/api/real/http';

interface LocalUserState {
  user: User | null;
  isLoading: boolean;
  error: string | null;
  fetchMe: () => Promise<void>;
  setUser: (user: User | null) => void;
  clearError: () => void;
}

export const useAuthStore = create<LocalUserState>((set) => ({
  user: null,
  isLoading: true,
  error: null,

  fetchMe: async () => {
    try {
      const api = getApi();
      const response = await api.me();
      clearLegacyTokenStorage();
      set({
        user: response.data,
        isLoading: false,
        error: null,
      });
    } catch (err) {
      set({
        user: null,
        isLoading: false,
        error: err instanceof Error ? err.message : '加载本地用户失败',
      });
    }
  },

  setUser: (user) => set({ user }),
  clearError: () => set({ error: null }),
}));
