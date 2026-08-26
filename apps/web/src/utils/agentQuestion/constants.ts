/**
 * 共享兜底选项与文案常量（§4.2.16 N-02 拆分）。
 *
 * 原 `agentQuestion.ts` 把 LEVEL_OPTS / LANG_OPTS / GOAL_OPTS 直接写在文件顶部，
 * 与归一化逻辑混在一起。拆分后只暴露给归一化/兜底链路使用，避免被外部直接依赖。
 */
import type { RadioOption } from '@/api/types';

/** 水平四档（初学 / 了解 / 掌握 / 精通） */
export const LEVEL_OPTS: RadioOption[] = [
  { value: 'beginner', label: '初学 · 刚接触' },
  { value: 'intermediate', label: '了解 · 能读简单代码' },
  { value: 'advanced', label: '掌握 · 能独立改功能' },
  { value: 'expert', label: '精通 · 能讲架构与设计' },
];

/** 主流技术栈（学习路径/摸底题通用兜底） */
export const LANG_OPTS: RadioOption[] = [
  { value: 'python', label: 'Python' },
  { value: 'typescript', label: 'TypeScript / JavaScript' },
  { value: 'csharp', label: 'C#' },
  { value: 'cpp', label: 'C / C++' },
  { value: 'go', label: 'Go' },
  { value: 'rust', label: 'Rust' },
  { value: 'other', label: '其他（可在下方补充）' },
];

/** 学习目标兜底 */
export const GOAL_OPTS: RadioOption[] = [
  { value: 'overview', label: '快速了解某个项目' },
  { value: 'learn', label: '系统学习 / 跟读源码' },
  { value: 'agent_dev', label: '学习 Agent / AI 应用开发' },
  { value: 'path', label: '规划学习路径' },
  { value: 'compare', label: '对比多个项目' },
];
