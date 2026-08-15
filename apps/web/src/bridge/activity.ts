/** 行为上报(§7.2 / §10.12):page_view 路由即发、pointer 1s 节流、
 * selection 500ms 去抖;privacy.activity_report=false 全静默(硬开关);
 * 一切失败静默(永不打扰主流程)。
 */

import { callCapability } from './client';

export type ActivityKind = 'page_view' | 'pointer' | 'selection' | 'manual';

const POINTER_INTERVAL_MS = 1000;
const SELECTION_DEBOUNCE_MS = 500;

let enabled = true;

/** 初始化时读一次隐私开关;设置变更经 settings.changed 事件刷新。 */
export function setActivityReportEnabled(v: boolean): void {
  enabled = v;
}

export function activityReportEnabled(): boolean {
  return enabled;
}

export async function initActivityReport(): Promise<void> {
  try {
    const item = await callCapability<{ value: boolean }>('settings', 'get_setting', {
      key: 'privacy.activity_report',
    });
    enabled = item.value !== false;
  } catch {
    enabled = true; // 读不到按默认开(§7.2 默认上报,用户可关)
  }
}

/** page_view:无节流,路由切换即发。 */
export function reportPageView(page: string): void {
  if (!enabled) return;
  reportActivity({ kind: 'page_view', page });
}

let lastPointerAt = 0;
/** pointer:hover/焦点目标;1s 节流(坑:高频事件,不节流会刷爆)。 */
export function reportPointer(page: string, target: string): void {
  if (!enabled) return;
  const now = Date.now();
  if (now - lastPointerAt < POINTER_INTERVAL_MS) return;
  lastPointerAt = now;
  reportActivity({ kind: 'pointer', page, detail: { target: target.slice(0, 120) } });
}

let selectionTimer: number | undefined;
let lastSelectionKey = '';
/** selection:文本选区;500ms 去抖 + 同文本不重发,截断 200 字。 */
export function reportSelection(page: string, text: string): void {
  if (!enabled) return;
  const clipped = text.slice(0, 200);
  if (clipped === lastSelectionKey) return;
  lastSelectionKey = clipped;
  window.clearTimeout(selectionTimer);
  selectionTimer = window.setTimeout(() => {
    reportActivity({ kind: 'selection', page, detail: { text: clipped } });
  }, SELECTION_DEBOUNCE_MS);
}

async function reportActivity(body: {
  kind: ActivityKind;
  page: string;
  detail?: Record<string, unknown>;
}): Promise<void> {
  try {
    await fetch('/api/activity', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    // 静默:上报永不打扰主流程
  }
}
