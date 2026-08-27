/** 液态玻璃层级 token —— class 字符串与 liquid-glass.css 单一对应。
 *
 * 三层语义：外层面板 / 内层 pill 控件 / 内层小控件(chip)。
 * 场景差异（圆角、间距）由各页面 CSS 覆盖，不在此处按页面复制常量。 */

/** 外层 · 面板级玻璃（0.05 tint / blur 10px / 无内发光） */
export const GLASS_OUTER = 'glass-card glass-card--overview-outer';

/** 内层 · 可交互 pill 控件（0.1 tint / blur 50px / 内发光 + hover 态） */
export const GLASS_INNER =
  'overview-control-surface glass-card glass-card--overview-inner liquid-glass--pill liquid-glass--interactive';

/** 内层 · 非交互小控件（头像/徽章/排名 chip，圆角由使用方 CSS 决定） */
export const GLASS_CHIP = 'glass-card glass-card--overview-inner';
