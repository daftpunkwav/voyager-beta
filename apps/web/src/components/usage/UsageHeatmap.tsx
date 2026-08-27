// @ts-nocheck — 迁移期:上游迁入的代码,字段重命名由 legacyApi 边界归一化,新 page / hook 仍按 strict 写(见各文件顶部注释)。
import { useMemo } from 'react';
import type { LlmUsageSummary } from '@/api/types';
import { GLASS_CHIP } from '@/constants/glassTokens';

interface UsageHeatmapProps {
  heatmap: LlmUsageSummary['heatmap'];
}

/** 本地日历日 YYYY-MM-DD（勿用 toISOString，会按 UTC 错日） */
function ymdLocal(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/** 将按日数据排成 GitHub 式周列（7 行 × N 周） */
function buildWeekColumns(heatmap: LlmUsageSummary['heatmap']) {
  if (!heatmap.length) return [] as Array<Array<(typeof heatmap)[number] | null>>;

  const byDate = new Map(heatmap.map((c) => [c.date, c]));
  const first = new Date(`${heatmap[0]?.date ?? ''}T12:00:00`);
  const last = new Date(`${heatmap[heatmap.length - 1]?.date ?? ''}T12:00:00`);

  // 对齐到周日开始
  const start = new Date(first);
  start.setDate(start.getDate() - start.getDay());

  const end = new Date(last);
  end.setDate(end.getDate() + (6 - end.getDay()));

  const columns: Array<Array<(typeof heatmap)[number] | null>> = [];
  const cursor = new Date(start);
  let col: Array<(typeof heatmap)[number] | null> = [];

  while (cursor <= end) {
    const key = ymdLocal(cursor);
    const inRange =
      key >= (heatmap[0]?.date ?? '') && key <= (heatmap[heatmap.length - 1]?.date ?? '');
    col.push(inRange ? byDate.get(key) ?? { date: key, calls: 0, intensity: 0 } : null);
    if (col.length === 7) {
      columns.push(col);
      col = [];
    }
    cursor.setDate(cursor.getDate() + 1);
  }
  if (col.length) columns.push(col);
  return columns;
}

function levelOf(intensity: number): 0 | 1 | 2 | 3 {
  if (intensity <= 0) return 0;
  if (intensity < 0.34) return 1;
  if (intensity < 0.67) return 2;
  return 3;
}

/** GitHub 风格活跃热力图（周列布局） */
export function UsageHeatmap({ heatmap }: UsageHeatmapProps) {
  const weeks = useMemo(() => buildWeekColumns(heatmap), [heatmap]);

  return (
    <div className={`${GLASS_CHIP} usage-panel usage-heat-panel`}>
      <div className="usage-panel-head">
        <h3 className="usage-panel-title">活跃热度图</h3>
        <div className="usage-heat-legend" aria-hidden>
          <span>较少</span>
          <span className="usage-heat-swatch" data-level="0" />
          <span className="usage-heat-swatch" data-level="1" />
          <span className="usage-heat-swatch" data-level="2" />
          <span className="usage-heat-swatch" data-level="3" />
          <span>较多</span>
        </div>
      </div>
      <div className="usage-heat-wrap">
        <div className="usage-heat-grid" role="img" aria-label="按日调用热力图">
          {weeks.map((week, wi) => (
            <div key={wi} className="usage-heat-week">
              {week.map((cell, di) =>
                cell ? (
                  <div
                    key={cell.date}
                    className="usage-heat-cell"
                    data-level={levelOf(cell.intensity)}
                    title={`${cell.date}: ${cell.calls} 次`}
                  />
                ) : (
                  <div key={`pad-${wi}-${di}`} className="usage-heat-cell is-pad" />
                ),
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
