import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { STORAGE, migrateKey } from '@/brand';

migrateKey(STORAGE.uiStore, STORAGE.legacy.uiStore);

export type Theme = 'dark' | 'light' | 'system';

export interface Toast {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  message: string;
  /** 报错码，用于渲染与查表 */
  code?: string;
  duration?: number;
}

interface UIState {
  theme: Theme;
  sidebarCollapsed: boolean;
  fontScale: number;
  toasts: Toast[];
  setTheme: (theme: Theme) => void;
  toggleSidebar: () => void;
  setFontScale: (scale: number) => void;
  addToast: (toast: Omit<Toast, 'id'>) => void;
  removeToast: (id: string) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      // 主题唯一真相在后端 appearance.theme(§10.11);本 store 只做 UI 选中态,
      // 由 shell/themeBridge 经 get_theme / settings.changed 回写对齐。
      // DOM 的 data-theme 也只由 themeBridge.applyTheme 一处应用。
      theme: 'system',
      sidebarCollapsed: false,
      fontScale: 1.0,
      toasts: [],

      setTheme: (theme) => {
        set({ theme });
      },

      toggleSidebar: () => {
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed }));
      },

      setFontScale: (scale) => {
        const clamped = Math.max(0.8, Math.min(1.5, scale));
        set({ fontScale: clamped });
        document.documentElement.style.setProperty('--font-scale', String(clamped));
      },

      addToast: (toast) => {
        const id = `toast_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
        const newToast: Toast = { ...toast, id };
        set((state) => ({ toasts: [...state.toasts, newToast] }));
      },

      removeToast: (id) => {
        set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
      },
    }),
    {
      name: STORAGE.uiStore,
      partialize: (state) => ({
        theme: state.theme,
        sidebarCollapsed: state.sidebarCollapsed,
        fontScale: state.fontScale,
      }),
      onRehydrateStorage: () => (state) => {
        if (state) {
          document.documentElement.style.setProperty(
            '--font-scale',
            String(state.fontScale)
          );
        }
      },
    }
  )
);
