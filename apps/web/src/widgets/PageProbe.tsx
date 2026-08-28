/** 页面感知组件:挂 AppShell,路由变化 -> page_view + 页摘要上报;
 * 30s 周期刷新摘要;选中变化即时上报。privacy 开关关闭时全静默。
 */

import { useEffect, useRef, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import { callCapability } from '@/bridge/client';
import {
  initActivityReport,
  activityReportEnabled,
  reportPageView,
} from '@/bridge/activity';
import { subscribe } from '@/bridge/stream';
import { PAGE_PROBES } from '@/shell/pageProbes';

const SUMMARY_INTERVAL_MS = 30_000;
const SELECTION_POLL_MS = 2000;
const INITIAL_DELAY_MS = 800;

export function PageProbe() {
  const location = useLocation();
  const lastSelected = useRef('');
  const timersRef = useRef<{ t1: number | null; summary: number | null; selection: number | null }>({
    t1: null,
    summary: null,
    selection: null,
  });

  useEffect(() => {
    void initActivityReport();
    // 设置热切换:关掉开关立即生效(不再发任何上报)
    return subscribe(['settings.changed'], (ev) => {
      if (ev.payload.key === 'privacy.activity_report') {
        import('@/bridge/activity').then((m) => {
          m.setActivityReportEnabled(ev.payload.value !== false);
        });
      }
    });
  }, []);

  // 统一清理当前路由下的所有定时器
  const clearTimers = useCallback(() => {
    const { t1, summary, selection } = timersRef.current;
    if (t1 != null) window.clearTimeout(t1);
    if (summary != null) window.clearInterval(summary);
    if (selection != null) window.clearInterval(selection);
    timersRef.current = { t1: null, summary: null, selection: null };
  }, []);

  const reportSummary = useCallback(() => {
    if (!activityReportEnabled()) return;
    const probe = PAGE_PROBES[location.pathname];
    if (!probe) return;
    const out = probe.report();
    if (!out) return; // 数据未就绪,不报空页(坑 2)
    lastSelected.current = out.selected ?? '';
    void callCapability('agent', 'report_page_context', {
      page: probe.page,
      summary: out.summary,
      counts: out.counts,
      selected: out.selected ?? '',
    }).catch(() => {
      // 静默
    });
  }, [location.pathname]);

  // 选中变化:轻轮询对比(避免侵入各页 store 订阅;选中变化频率低)
  const pollSelection = useCallback(() => {
    if (!activityReportEnabled()) return;
    const probe = PAGE_PROBES[location.pathname];
    if (!probe) return;
    const out = probe.report();
    const sel = out?.selected ?? '';
    if (out && sel !== lastSelected.current) {
      lastSelected.current = sel;
      void callCapability('agent', 'report_page_context', {
        page: probe.page,
        summary: out.summary,
        counts: out.counts,
        selected: sel,
      }).catch(() => {});
    }
  }, [location.pathname]);

  useEffect(() => {
    clearTimers();
    if (!activityReportEnabled()) return;
    reportPageView(location.pathname);
    // 等页面数据拉起再报摘要(首拍延后一拍)
    timersRef.current.t1 = window.setTimeout(reportSummary, INITIAL_DELAY_MS);
    timersRef.current.summary = window.setInterval(reportSummary, SUMMARY_INTERVAL_MS);
    timersRef.current.selection = window.setInterval(pollSelection, SELECTION_POLL_MS);
    return clearTimers;
  }, [location.pathname, clearTimers, reportSummary, pollSelection]);

  return null;
}
