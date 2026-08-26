/** 总览外层 · 0.05 tint / blur 10px / 无内发光 */
export const OVERVIEW_OUTER_GLASS = 'glass-card glass-card--overview-outer';

/** Hero / Agent 卡外层 · 与四宫格同参 */
export const HERO_OUTER_GLASS = OVERVIEW_OUTER_GLASS;

/** 总览内层 pill · 0.1 tint / blur 50px / 内发光 2px 1px */
export const OVERVIEW_INNER_GLASS =
  'overview-control-surface glass-card glass-card--overview-inner liquid-glass--pill liquid-glass--interactive';

/** Hero 快捷按钮 / Agent meta / 轮播导航 · 与列表条目同参 */
export const HERO_INNER_GLASS = OVERVIEW_INNER_GLASS;

/** Mentor 周报内层 */
export const OVERVIEW_SUMMARY_INNER_GLASS = OVERVIEW_INNER_GLASS;

/** 头像 / 徽章 / 排名等小控件 · 内层玻璃（圆角由 overview.css 覆盖） */
export const OVERVIEW_CHIP_GLASS = 'glass-card glass-card--overview-inner';
