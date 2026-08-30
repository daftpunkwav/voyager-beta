/** 主题桥(§10.11 单一真相):后端 appearance.theme 是唯一事实来源。
 *
 * 本文件是 data-theme 的**唯一应用点**(uiStore 不再操作 DOM):
 * - 启动 get_theme → applyTheme + 回写 uiStore(避免 DOM dark / store light 的双源漂移);
 * - settings.changed(含用户与 agent 改主题)→ applyTheme + 回写 uiStore;
 * - system 模式跟随 OS 的 prefers-color-scheme。
 * 用户切换入口(Topbar / 设置页)先 set_theme 落库,成功后经本桥统一生效。
 */

import { useEffect } from 'react';
import { callCapability } from '@/bridge/client';
import { subscribe } from '@/bridge/stream';
import { useUIStore, type Theme } from '@/stores/uiStore';

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

/** 唯一的 DOM 主题应用:始终落 data-theme=light|dark(不 removeAttribute)。 */
export function applyTheme(theme: string): void {
  const resolved = resolve(theme);
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themeRequested = theme;
}

/** 后端事实来源 → DOM + store 选中态,一次对齐(启动与热更新共用)。 */
export function syncTheme(theme: string): void {
  applyTheme(theme);
  if (['light', 'dark', 'system'].includes(theme)) {
    useUIStore.getState().setTheme(theme as Theme);
  }
}

export function applyFontScale(scale: number): void {
  // 使用 CSS 变量实现全局字体缩放,避免 body.style.zoom 在部分浏览器/高分屏下
  // 导致布局模糊、定位偏移及像素不对齐问题。
  document.documentElement.style.setProperty('--font-scale', String(scale));
}

export function useThemeBridge() {
  useEffect(() => {
    let alive = true;
    callCapability<{ theme: string; font_scale: number }>('settings', 'get_theme')
      .then((t) => {
        if (alive && t) {
          syncTheme(t.theme);
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
    onSchemeChange();
    media.addEventListener('change', onSchemeChange);

    const off = subscribe(['settings.changed'], (event) => {
      const payload = event.payload as ThemePayload;
      if (payload.key === 'appearance.theme' && typeof payload.value === 'string') {
        syncTheme(payload.value);
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
