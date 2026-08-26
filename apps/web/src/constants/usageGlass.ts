/** 用量页玻璃常量 —— 与总览内外层同源 */
export {
  OVERVIEW_OUTER_GLASS as USAGE_OUTER_GLASS,
  OVERVIEW_INNER_GLASS as USAGE_INNER_GLASS,
  OVERVIEW_CHIP_GLASS as USAGE_CHIP_GLASS,
} from '@/constants/overviewGlass';

/** 图表配色（暗色液态玻璃） */
export const USAGE_CHART_COLORS = [
  '#5b8def',
  '#3ecf8e',
  '#a78bfa',
  '#f87171',
  '#fb923c',
  '#22d3ee',
  '#f472b6',
  '#94a3b8',
] as const;

export const USAGE_TOKEN_COLORS = {
  cached: '#3ecf8e',
  uncached: '#5b8def',
  completion: '#fb923c',
} as const;
