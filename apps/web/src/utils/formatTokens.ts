/** Token 数量展示（中文单位） */
export function formatTokenCount(n: number | undefined | null): string {
  const v = Number(n) || 0;
  if (v >= 100_000_000) return `${(v / 100_000_000).toFixed(1)}亿`;
  if (v >= 10_000) return `${(v / 10_000).toFixed(1)}万`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return String(Math.round(v));
}

export function formatTokenPercent(part: number, total: number): string {
  if (!total) return '0%';
  const pct = (part / total) * 100;
  if (pct >= 10) return `${pct.toFixed(0)}%`;
  return `${pct.toFixed(1)}%`;
}
