/** 页面感知组件:挂 AppShell,路由变化 -> page_view + 页摘要上报;
 * 30s 周期刷新摘要;选中变化即时上报。privacy 开关关闭时全静默。
 */

import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { callCapability } from '@/bridge/client';
import {
  initActivityReport,
  activityReportEnabled,
  reportPageView,
} from '@/bridge/activity';
import { subscribe } from '@/bridge/stream';
import { PAGE_PROBES } from './probes';

const SUMMARY_INTERVAL_MS = 30_000;

export function PageProbe() {
  const location = useLocation();
  const lastSelected = useRef('');

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

  // 摘要上报(读 probe 注册表;未注册页面静默跳过)
  const reportSummary = () => {
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
  };

  useEffect(() => {
    if (!activityReportEnabled()) return;
    reportPageView(location.pathname);
    // 等页面数据拉起再报摘要(首拍延后一拍)
    const t1 = window.setTimeout(reportSummary, 800);
    const timer = window.setInterval(reportSummary, SUMMARY_INTERVAL_MS);
    return () => {
      window.clearTimeout(t1);
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  // 选中变化:轻轮询对比(避免侵入各页 store 订阅;选中变化频率低)
  useEffect(() => {
    const timer = window.setInterval(() => {
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
    }, 2000);
    return () => window.clearInterval(timer);
  }, [location.pathname]);

  return null;
}
