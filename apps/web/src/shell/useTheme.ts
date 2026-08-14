/** 主题应用与热切换:settings.changed 事件驱动,用户手点与 agent 写入走同一通道。 */

import { useEffect } from 'react';
import { callCapability } from '@/bridge/client';
import { subscribe } from '@/bridge/stream';

interface ThemePayload {
  key?: string;
  value?: unknown;
}

function resolve(theme: string): 'light' | 'dark' {
  if (theme === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return theme === 'dark' ? 'dark' : 'light';
}

export function applyTheme(theme: string): void {
  document.documentElement.dataset.theme = resolve(theme);
}

export function applyFontScale(scale: number): void {
  // 全局缩放:zoom 连布局等比缩放,对 px 为单位的 token 体系零侵入
  document.body.style.zoom = String(scale);
}

export function useTheme() {
  useEffect(() => {
    let alive = true;
    callCapability<{ theme: string; font_scale: number }>('settings', 'get_theme')
      .then((t) => {
        if (alive && t) {
          document.documentElement.dataset.themeRequested = t.theme;
          applyTheme(t.theme);
          applyFontScale(t.font_scale);
        }
      })
      .catch(() => {
        // 读不到设置(如后端未起)保持默认,不打断壳渲染
      });

    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const onSchemeChange = () => {
      // system 模式跟随系统;其他主题该监听无效果
      if (document.documentElement.dataset.themeRequested === 'system') {
        document.documentElement.dataset.theme = media.matches ? 'dark' : 'light';
      }
    };
    media.addEventListener('change', onSchemeChange);

    const off = subscribe(['settings.changed'], (event) => {
      const payload = event.payload as ThemePayload;
      if (payload.key === 'appearance.theme' && typeof payload.value === 'string') {
        document.documentElement.dataset.themeRequested = payload.value;
        applyTheme(payload.value);
      }
      if (payload.key === 'appearance.font_scale' && typeof payload.value === 'number') {
        applyFontScale(payload.value);
      }
    });

    return () => {
      alive = false;
      media.removeEventListener('change', onSchemeChange);
      off();
    };
  }, []);
}
