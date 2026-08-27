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
