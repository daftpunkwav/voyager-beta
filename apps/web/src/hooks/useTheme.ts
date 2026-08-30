import { useSyncExternalStore } from 'react';
import { callCapability } from '@/bridge/client';
import { applyTheme } from '@/shell/themeBridge';
import { useUIStore } from '@/stores/uiStore';

/**
 * 主题与字体缩放
 *
 * 主题唯一真相在后端 appearance.theme(§10.11):切换必须先 set_theme 落库
 * (system 也写后端),成功后回写 UI 选中态并立即应用 DOM(不等 settings.changed,
 * 与事件回放幂等)。状态来自 UI store(选中态),与 LLM settings 无关。
 * 2026-07-09 review 后从 useSettings.ts 独立成模块;2026-08-30 phase-06 改为唯一写入。
 */
export function useTheme() {
  const theme = useUIStore((s) => s.theme);
  const fontScale = useUIStore((s) => s.fontScale);
  const setFontScale = useUIStore((s) => s.setFontScale);

  /** 切换主题:先落库后端,成功再改选中态与视觉;失败原样抛出由调用方提示。 */
  const changeTheme = async (next: typeof theme) => {
    await callCapability('settings', 'set_theme', { theme: next });
    useUIStore.getState().setTheme(next);
    applyTheme(next);
  };

  return { theme, changeTheme, fontScale, setFontScale };
}

function readSystemPrefersDark(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false;
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function subscribeSystemTheme(callback: () => void): () => void {
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  mq.addEventListener('change', callback);
  return () => mq.removeEventListener('change', callback);
}

/** 当前是否处于深色视觉（含 system 跟随） */
export function useIsDarkTheme(): boolean {
  const theme = useUIStore((s) => s.theme);
  const systemDark = useSyncExternalStore(
    subscribeSystemTheme,
    readSystemPrefersDark,
    () => false
  );

  return theme === 'dark' || (theme === 'system' && systemDark);
}
