// @ts-nocheck — 迁移期:RepoPilot 风格代码,新 page / hook 仍按 strict 写(见各文件顶部注释)。
import type { ProjectProgress } from '@/api/types';
import { progressLabel } from '@/utils/labels';

interface ProgressBadgeProps {
  progress: ProjectProgress;
}

/** 原型使用 progress-pill + progress-{state} */
export function ProgressBadge({ progress }: ProgressBadgeProps) {
  return (
    <span className={`progress-pill progress-${progress}`}>{progressLabel(progress)}</span>
  );
}
