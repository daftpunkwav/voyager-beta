// @ts-nocheck — 迁移期:上游迁入的代码,字段重命名由 legacyApi 边界归一化,新 page / hook 仍按 strict 写(见各文件顶部注释)。
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getApi } from '@/api/client';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import {
  USAGE_CHIP_GLASS,
  USAGE_INNER_GLASS,
  USAGE_OUTER_GLASS,
} from '@/constants/usageGlass';
import { formatTokenCount } from '@/utils/formatTokens';
import { UsageDonut } from './UsageDonut';
import { UsageHeatmap } from './UsageHeatmap';
import { UsageKpiCards } from './UsageKpiCards';
import { UsageStackedBars } from './UsageStackedBars';

const DAYS_OPTIONS = [7, 30] as const;

function fmtTs(ts: string | null): string {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleString('zh-CN', {
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return ts;
  }
}

/** 一屏用量仪表盘 */
export function LlmUsageDashboard() {
  const [days, setDays] = useState<(typeof DAYS_OPTIONS)[number]>(30);

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['llm-usage', days],
    queryFn: () => getApi().getLlmUsage(days),
  });

  const usage = data?.data;

  return (
    <section className={`usage-dashboard ${USAGE_OUTER_GLASS}`}>
      <div className="usage-toolbar">
        <div className="usage-toolbar-left">
          <span className="usage-toolbar-label">时间范围</span>
          <div className={`layout-switch ${USAGE_INNER_GLASS}`}>
            {DAYS_OPTIONS.map((d) => (
              <button
                key={d}
                type="button"
                className={days === d ? 'active' : ''}
                onClick={() => setDays(d)}
              >
                最近 {d} 天
              </button>
            ))}
          </div>
        </div>
        <button
          type="button"
          className={`btn btn-sm ${USAGE_INNER_GLASS}`}
          disabled={isFetching}
          onClick={() => void refetch()}
        >
          刷新
        </button>
      </div>

      {isLoading && <LoadingSpinner />}
      {isError && (
        <p className="usage-error">[LLM_USAGE_MODULE_DOWN] 用量统计服务暂不可用</p>
      )}

      {usage && (
        <div className="usage-dashboard-body">
          <UsageKpiCards usage={usage} />
          <div className="usage-mid-row">
            <UsageHeatmap heatmap={usage.heatmap} />
            <UsageDonut usage={usage} />
          </div>
          <UsageStackedBars usage={usage} />
          {usage.recent.length > 0 ? (
            <div className={`${USAGE_CHIP_GLASS} usage-recent`}>
              <h3 className="usage-panel-title">最近调用</h3>
              <ul className="usage-recent-list">
                {usage.recent.slice(0, 5).map((call) => (
                  <li key={call.id}>
                    <span className="usage-recent-ts">{fmtTs(call.created_at)}</span>
                    <span className="usage-recent-model">
                      {call.label ||
                        (call.provider && call.provider !== 'unknown'
                          ? `${call.provider}/${call.model}`
                          : call.model)}
                    </span>
                    {call.agent_id ? (
                      <span className="badge">{call.agent_id}</span>
                    ) : null}
                    <span className="usage-recent-tokens">
                      命中 {formatTokenCount(call.prompt_cached_tokens)} · 未命中{' '}
                      {formatTokenCount(call.prompt_uncached_tokens)} · 出{' '}
                      {formatTokenCount(call.completion_tokens)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}
