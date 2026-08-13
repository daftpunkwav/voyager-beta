/**
 * 图谱标签疏密度：预算、优先级、屏幕空间去重叠
 */

export const LABEL_KIND_WEIGHT: Record<string, number> = {
  Project: 80,
  Package: 60,
  Module: 55,
  Folder: 50,
  File: 40,
  Class: 35,
  Interface: 32,
  Route: 30,
  Function: 28,
  Method: 24,
  Type: 18,
  Field: 8,
  Variable: 6,
  Macro: 6,
  Section: 4,
  Decorator: 4,
};

export function labelPriority(node: {
  kind?: string;
  label?: string;
  size?: number;
  in_calls?: number;
}): number {
  const kind = node.kind || node.label || '';
  const kindBonus = LABEL_KIND_WEIGHT[kind] ?? 10;
  return (node.in_calls || 0) * 12 + (node.size || 0) * 2 + kindBonus;
}

/** 相机越远标签越少，避免星系全景糊成一片字 */
export function labelBudgetForDistance(dist: number, maxLabels: number): number {
  if (!Number.isFinite(dist) || dist <= 0) return Math.min(16, maxLabels);
  if (dist >= 2500) return Math.min(8, maxLabels);
  if (dist >= 1600) return Math.min(14, maxLabels);
  if (dist >= 900) return Math.min(22, maxLabels);
  if (dist >= 450) return Math.min(32, maxLabels);
  return Math.min(maxLabels, 40);
}

/** 世界字号：略随距离放大以便可读，但硬封顶，禁止全景巨幅叠字 */
export function labelWorldFontSize(dist: number, nodeSize: number): number {
  const byNode = Math.max(1.6, (nodeSize || 4) * 0.38);
  const byDist = Math.min(14, dist * 0.0065);
  return Math.min(14, Math.max(byNode, byDist));
}

export interface ProjectedLabel {
  id: number;
  x: number;
  y: number;
  w: number;
  h: number;
  priority: number;
}

/** 按优先级贪心保留互不重叠的标签（屏幕像素坐标） */
export function pickNonOverlappingLabels(
  items: ProjectedLabel[],
  maxKeep: number,
  padding = 4,
): Set<number> {
  const sorted = [...items].sort((a, b) => b.priority - a.priority);
  const kept: ProjectedLabel[] = [];
  const ids = new Set<number>();

  for (const item of sorted) {
    if (ids.size >= maxKeep) break;
    const overlaps = kept.some(
      (k) =>
        Math.abs(k.x - item.x) * 2 < k.w + item.w + padding &&
        Math.abs(k.y - item.y) * 2 < k.h + item.h + padding,
    );
    if (overlaps) continue;
    kept.push(item);
    ids.add(item.id);
  }
  return ids;
}

/** 展示名：去掉包裹引号，过长截断由贴图侧再处理 */
export function shortenLabelName(raw: string): string {
  let s = (raw || '').trim();
  if (
    (s.startsWith('"') && s.endsWith('"')) ||
    (s.startsWith("'") && s.endsWith("'"))
  ) {
    s = s.slice(1, -1);
  }
  if (s.includes('/') && !s.includes(' ')) {
    const parts = s.split('/');
    s = parts[parts.length - 1] || s;
  }
  return s;
}
