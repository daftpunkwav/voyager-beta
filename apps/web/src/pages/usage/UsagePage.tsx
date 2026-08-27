import { LlmUsageDashboard } from '@/components/usage/LlmUsageDashboard';

/** LLM 用量独立页 —— 一屏仪表盘 */
export function UsagePage() {
  return (
    <div className="usage-page page-scaffold">
      <header className="page-scaffold__head">
        <div>
          <h1>用量</h1>
          <p className="page-scaffold__subtitle">LLM 调用统计、模型分布与热力趋势</p>
        </div>
      </header>
      <div className="page-scaffold__body">
        <LlmUsageDashboard />
      </div>
    </div>
  );
}
