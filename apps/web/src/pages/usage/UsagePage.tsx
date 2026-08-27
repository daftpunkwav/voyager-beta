import { LlmUsageDashboard } from '@/components/usage/LlmUsageDashboard';

/** LLM 用量独立页 —— 一屏仪表盘 */
export function UsagePage() {
  return (
    <div className="usage-page page-scaffold">
      <div className="page-scaffold__body">
        <LlmUsageDashboard />
      </div>
    </div>
  );
}
