import { useMemo, useState } from 'react';
import type { LlmUsageSummary } from '@/api/types';
import { GLASS_CHIP } from '@/constants/glassTokens';
import { USAGE_CHART_COLORS, USAGE_TOKEN_COLORS } from '@/constants/usageChartColors';
import { formatTokenCount } from '@/utils/formatTokens';

type BarMode = 'io' | 'model';

interface UsageStackedBarsProps {
  usage: LlmUsageSummary;
}

interface NormalizedDay {
  date: string;
  total_tokens: number;
  prompt_cached_tokens: number;
  prompt_uncached_tokens: number;
  completion_tokens: number;
  by_model: Array<{ model: string; total_tokens: number }>;
}

function normalizeDays(usage: LlmUsageSummary): NormalizedDay[] {
  return usage.by_day.map((d) => ({
    date: d.date,
    total_tokens: d.total_tokens ?? d.input + d.output,
    prompt_cached_tokens:
      d.prompt_cached_tokens ?? Math.round((d.input ?? 0) * 0.3),
    prompt_uncached_tokens:
      d.prompt_uncached_tokens ?? Math.round((d.input ?? 0) * 0.7),
    completion_tokens: d.completion_tokens ?? d.output ?? 0,
    by_model: d.by_model?.map((m) => ({ model: m.model, total_tokens: m.total_tokens ?? m.input + m.output })) ?? [],
  }));
}

export function UsageStackedBars({ usage }: UsageStackedBarsProps) {
  const [mode, setMode] = useState<BarMode>('io');
  const days = useMemo(() => normalizeDays(usage), [usage]);

  const maxTotal = useMemo(
    () => Math.max(...days.map((d) => d.total_tokens), 1),
    [days],
  );

  const modelKeys = useMemo(() => {
    const set = new Set<string>();
    for (const d of days) {
      for (const m of d.by_model) set.add(m.model);
    }
    return [...set].slice(0, 6);
  }, [days]);

  return (
    <div className={`${GLASS_CHIP} usage-panel usage-bars-panel`}>
      <div className="usage-panel-head">
        <h3 className="usage-panel-title">按天 Token 趋势</h3>
        <div className="layout-switch usage-mode-switch">
          <button
            type="button"
            className={mode === 'io' ? 'active' : ''}
            onClick={() => setMode('io')}
          >
            命中/未命中/输出
          </button>
          <button
            type="button"
            className={mode === 'model' ? 'active' : ''}
            onClick={() => setMode('model')}
          >
            按模型
          </button>
        </div>
      </div>

      <div className="usage-bars" role="img" aria-label="按天 Token 堆叠柱">
        {days.map((d) => {
          const h = Math.max(4, Math.round((d.total_tokens / maxTotal) * 100));
          if (mode === 'io') {
            const sum =
              d.prompt_cached_tokens +
                d.prompt_uncached_tokens +
                d.completion_tokens || 1;
            const cPct = (d.prompt_cached_tokens / sum) * 100;
            const uPct = (d.prompt_uncached_tokens / sum) * 100;
            const oPct = (d.completion_tokens / sum) * 100;
            return (
              <div key={d.date} className="usage-bar-col" title={`${d.date}: ${formatTokenCount(d.total_tokens)}`}>
                <div className="usage-bar-stack" style={{ height: `${h}%` }}>
                  <div style={{ flex: cPct, background: USAGE_TOKEN_COLORS.cached }} />
                  <div style={{ flex: uPct, background: USAGE_TOKEN_COLORS.uncached }} />
                  <div style={{ flex: oPct, background: USAGE_TOKEN_COLORS.completion }} />
                </div>
                <span className="usage-bar-label">{d.date.slice(5)}</span>
              </div>
            );
          }
          const parts = modelKeys.map((key, i) => {
            const tok = d.by_model.find((m) => m.model === key)?.total_tokens ?? 0;
            return { key, tok, color: USAGE_CHART_COLORS[i % USAGE_CHART_COLORS.length] };
          });
          const partSum = parts.reduce((s, p) => s + p.tok, 0) || 1;
          return (
            <div key={d.date} className="usage-bar-col" title={`${d.date}: ${formatTokenCount(d.total_tokens)}`}>
              <div className="usage-bar-stack" style={{ height: `${h}%` }}>
                {parts.map((p) => (
                  <div
                    key={p.key}
                    style={{ flex: (p.tok / partSum) * 100, background: p.color }}
                  />
                ))}
              </div>
              <span className="usage-bar-label">{d.date.slice(5)}</span>
            </div>
          );
        })}
        {days.length === 0 ? <p className="usage-empty-hint">暂无趋势数据</p> : null}
      </div>

      <div className="usage-bars-legend">
        {mode === 'io' ? (
          <>
            <span>
              <i className="usage-dot" style={{ background: USAGE_TOKEN_COLORS.cached }} />
              输入命中
            </span>
            <span>
              <i className="usage-dot" style={{ background: USAGE_TOKEN_COLORS.uncached }} />
              输入未命中
            </span>
            <span>
              <i className="usage-dot" style={{ background: USAGE_TOKEN_COLORS.completion }} />
              输出
            </span>
          </>
        ) : (
          modelKeys.map((k, i) => (
            <span key={k}>
              <i
                className="usage-dot"
                style={{ background: USAGE_CHART_COLORS[i % USAGE_CHART_COLORS.length] }}
              />
              {k}
            </span>
          ))
        )}
      </div>
    </div>
  );
}
