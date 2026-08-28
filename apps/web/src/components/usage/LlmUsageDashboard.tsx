import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getApi } from '@/api/client';
import type { LlmUsageSummary } from '@/api/types';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { BACKEND_UNREACHABLE } from '@/utils/errors';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { GLASS_CHIP, GLASS_INNER, GLASS_OUTER } from '@/constants/glassTokens';
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

function normalizeUsage(raw: unknown): LlmUsageSummary {
  const u = raw as Partial<LlmUsageSummary>;
  const byModel = Array.isArray(u.by_model)
    ? u.by_model.map((m) => ({
        model: m.model ?? 'unknown',
        label: m.label,
        provider: m.provider,
        input: m.input ?? 0,
        output: m.output ?? 0,
        total_tokens: m.total_tokens ?? m.input + m.output,
        calls: m.calls ?? 0,
        cost: m.cost ?? 0,
      }))
    : [];
  const byDay = Array.isArray(u.by_day)
    ? u.by_day.map((d) => ({
        date: d.date ?? '',
        input: d.input ?? 0,
        output: d.output ?? 0,
        total_tokens: d.total_tokens ?? d.input + d.output,
        prompt_cached_tokens: d.prompt_cached_tokens,
        prompt_uncached_tokens: d.prompt_uncached_tokens,
        completion_tokens: d.completion_tokens,
        calls: d.calls ?? 0,
        cost: d.cost ?? 0,
        by_model: d.by_model,
      }))
    : [];
  const totalInput = u.total_input_tokens ?? byDay.reduce((s, d) => s + d.input, 0);
  const totalOutput = u.total_output_tokens ?? byDay.reduce((s, d) => s + d.output, 0);
  return {
    total_input_tokens: totalInput,
    total_output_tokens: totalOutput,
    total_cost: u.total_cost ?? 0,
    by_model: byModel,
    by_day: byDay,
    totals: u.totals,
    top: u.top,
    by_provider: u.by_provider,
    heatmap: u.heatmap,
    recent: u.recent,
  };
}

/** 一屏用量仪表盘 */
export function LlmUsageDashboard() {
  const [days, setDays] = useState<(typeof DAYS_OPTIONS)[number]>(30);

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['llm-usage', days],
    queryFn: async () => {
      const res = await getApi().getLlmUsage(days);
      return normalizeUsage(res.data);
    },
  });

  const usage = data;

  return (
    <section className={`usage-dashboard ${GLASS_OUTER}`}>
      {isLoading && (
        <div className="page-scaffold__state">
          <LoadingSpinner label="加载用量统计中…" />
        </div>
      )}
      {isError && (
        <div className="page-scaffold__state">
          <EmptyState
            title="用量统计服务暂不可用"
            description={(error as Error | null)?.message || BACKEND_UNREACHABLE}
            icon={EmptyStateIcons.usage}
            onRetry={() => void refetch()}
          />
        </div>
      )}

      {usage && (
        <>
          <div className="usage-toolbar">
            <div className="usage-toolbar-left">
              <span className="usage-toolbar-label">时间范围</span>
              <div className={`layout-switch ${GLASS_INNER}`}>
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
              className={`btn btn-sm ${GLASS_INNER}`}
              disabled={isFetching}
              onClick={() => void refetch()}
            >
              刷新
            </button>
          </div>

          <div className="usage-dashboard-body">
          <UsageKpiCards usage={usage} />
          <div className="usage-mid-row">
            <UsageHeatmap heatmap={usage.heatmap} />
            <UsageDonut usage={usage} />
          </div>
          <UsageStackedBars usage={usage} />
          {usage.recent && usage.recent.length > 0 ? (
            <div className={`${GLASS_CHIP} usage-recent`}>
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
        </>
      )}
    </section>
  );
}
