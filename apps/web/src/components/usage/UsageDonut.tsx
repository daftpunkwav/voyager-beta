// @ts-nocheck — 迁移期:上游迁入的代码,字段重命名由 legacyApi 边界归一化,新 page / hook 仍按 strict 写(见各文件顶部注释)。
import { useMemo, useState } from 'react';
import type { LlmUsageSummary } from '@/api/types';
import { USAGE_CHART_COLORS, USAGE_CHIP_GLASS } from '@/constants/usageGlass';
import { formatTokenCount, formatTokenPercent } from '@/utils/formatTokens';

type DonutMode = 'model' | 'provider';

interface UsageDonutProps {
  usage: LlmUsageSummary;
}

interface Slice {
  key: string;
  tokens: number;
  color: string;
}

function polar(cx: number, cy: number, r: number, angle: number) {
  const rad = ((angle - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function arcPath(cx: number, cy: number, r: number, start: number, end: number) {
  const s = polar(cx, cy, r, end);
  const e = polar(cx, cy, r, start);
  const large = end - start <= 180 ? 0 : 1;
  return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large} 0 ${e.x} ${e.y}`;
}

export function UsageDonut({ usage }: UsageDonutProps) {
  const [mode, setMode] = useState<DonutMode>('model');

  const slices: Slice[] = useMemo(() => {
    const rows =
      mode === 'model'
        ? usage.by_model.map((r) => ({
            key: r.label || r.model,
            tokens: r.total_tokens,
          }))
        : usage.by_provider.map((r) => ({
            key: r.provider || '(unknown)',
            tokens: r.total_tokens,
          }));
    const sorted = [...rows].sort((a, b) => b.tokens - a.tokens);
    const top = sorted.slice(0, 5);
    const rest = sorted.slice(5).reduce((s, r) => s + r.tokens, 0);
    const list = [...top];
    if (rest > 0) list.push({ key: '其他', tokens: rest });
    return list.map((r, i) => ({
      ...r,
      color: USAGE_CHART_COLORS[i % USAGE_CHART_COLORS.length] ?? '#8e8e93',
    }));
  }, [usage, mode]);

  const total = slices.reduce((s, x) => s + x.tokens, 0) || usage.totals.total_tokens;
  const cx = 70;
  const cy = 70;
  const r = 52;
  const stroke = 16;

  let angle = 0;
  const arcs =
    total <= 0
      ? []
      : slices.map((slice) => {
          const sweep = (slice.tokens / total) * 360;
          const start = angle;
          const end = angle + Math.max(sweep, slice.tokens > 0 ? 0.5 : 0);
          angle = end;
          return { ...slice, start, end };
        });

  return (
    <div className={`${USAGE_CHIP_GLASS} usage-panel usage-donut-panel`}>
      <div className="usage-panel-head">
        <h3 className="usage-panel-title">模型用量</h3>
        <div className="layout-switch usage-mode-switch">
          <button
            type="button"
            className={mode === 'model' ? 'active' : ''}
            onClick={() => setMode('model')}
          >
            模型
          </button>
          <button
            type="button"
            className={mode === 'provider' ? 'active' : ''}
            onClick={() => setMode('provider')}
          >
            供应商
          </button>
        </div>
      </div>
      <div className="usage-donut-body">
        <svg viewBox="0 0 140 140" className="usage-donut-svg" aria-hidden>
          <circle
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke="rgba(255,255,255,0.06)"
            strokeWidth={stroke}
          />
          {arcs.map((a) =>
            a.tokens <= 0 ? null : (
              <path
                key={a.key}
                d={arcPath(cx, cy, r, a.start, a.end)}
                fill="none"
                stroke={a.color}
                strokeWidth={stroke}
                strokeLinecap="butt"
              />
            ),
          )}
          <text x={cx} y={cy - 4} textAnchor="middle" className="usage-donut-center-value">
            {formatTokenCount(total)}
          </text>
          <text x={cx} y={cy + 14} textAnchor="middle" className="usage-donut-center-unit">
            tokens
          </text>
        </svg>
        <ul className="usage-donut-legend">
          {slices.map((s) => (
            <li key={s.key}>
              <span className="usage-dot" style={{ background: s.color }} />
              <div className="usage-donut-legend-text">
                <div className="usage-donut-legend-row">
                  <span className="usage-donut-name">{s.key}</span>
                  <span className="usage-donut-pct">
                    {formatTokenPercent(s.tokens, total)}
                  </span>
                </div>
                <span className="usage-donut-tokens">
                  {formatTokenCount(s.tokens)} tokens
                </span>
              </div>
            </li>
          ))}
          {slices.length === 0 ? (
            <li className="usage-empty-hint">暂无用量数据</li>
          ) : null}
        </ul>
      </div>
    </div>
  );
}
