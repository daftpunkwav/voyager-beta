import { create } from 'zustand';
import { persist } from 'zustand/middleware';

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

function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === 'system') {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (prefersDark) {
      root.setAttribute('data-theme', 'dark');
    } else {
      root.removeAttribute('data-theme');
    }
  } else if (theme === 'dark') {
    root.setAttribute('data-theme', 'dark');
  } else {
    root.removeAttribute('data-theme');
  }
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      theme: 'light',
      sidebarCollapsed: false,
      fontScale: 1.0,
      toasts: [],

      setTheme: (theme) => {
        set({ theme });
        applyTheme(theme);
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
      name: 'rp-ui-store',
      partialize: (state) => ({
        theme: state.theme,
        sidebarCollapsed: state.sidebarCollapsed,
        fontScale: state.fontScale,
      }),
      onRehydrateStorage: () => (state) => {
        if (state) {
          applyTheme(state.theme);
          document.documentElement.style.setProperty(
            '--font-scale',
            String(state.fontScale)
          );
        }
      },
    }
  )
);

export { applyTheme };
