import { useEffect, useState } from 'react';
import { useUIStore } from '@/stores/uiStore';

/**
 * 主题与字体缩放
 *
 * 状态来自 UI store（持久化），与 LLM settings 无关。
 * 2026-07-09 review 后从 useSettings.ts 独立成模块。
 */
export function useTheme() {
  const theme = useUIStore((s) => s.theme);
  const setTheme = useUIStore((s) => s.setTheme);
  const fontScale = useUIStore((s) => s.fontScale);
  const setFontScale = useUIStore((s) => s.setFontScale);

  return { theme, setTheme, fontScale, setFontScale };
}

function readSystemPrefersDark(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false;
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

/** 当前是否处于深色视觉（含 system 跟随） */
export function useIsDarkTheme(): boolean {
  const theme = useUIStore((s) => s.theme);
  const [systemDark, setSystemDark] = useState(readSystemPrefersDark);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const update = () => setSystemDark(mq.matches);
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, []);

  return theme === 'dark' || (theme === 'system' && systemDark);
}
