/** 用量页:汇总卡三张(输入/输出 token、调用次数)+ 按模型表 + 调用占比条。
 * 数据只经 llm.get_usage_stats 能力读(不直读 usage 表,脱耦);
 * 成本金额估算留待 llm catalog 有 price 字段后(阶段 07 不做)。
 */

import { useEffect } from 'react';
import { Degraded } from '@/shell/Degraded';
import { useUsageStore, type UsageWindow } from './usageStore';

const WINDOWS: UsageWindow[] = [7, 30, 90];

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 10_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

/** 调用占比条(纯 CSS,不引图表库):按模型 calls 占比着色堆叠。 */
const BAR_COLORS = ['#0064d6', '#5e5ce6', '#bf5af2', '#ff9f0a', '#30d158', '#64d2ff'];

export function UsagePage() {
  const { loading, error, days, stats, init, setDays } = useUsageStore();

  useEffect(() => {
    void init();
  }, [init]);

  if (error) {
    return (
      <Degraded
        code={error.code}
        message={`用量数据不可用:${error.message}`}
        hint="其余页面不受影响"
        onRetry={() => void init()}
      />
    );
  }

  const totalCalls = stats?.calls ?? 0;
  const byModel = stats?.by_model ?? [];

  return (
    <section className="usage-page">
      <div className="sources-toolbar">
        <span className="label">用量统计</span>
        <span className="sources-toolbar__spacer" />
        {WINDOWS.map((w) => (
          <button
            key={w}
            type="button"
            className={`btn btn-sm ${days === w ? 'btn-primary' : ''}`}
            onClick={() => setDays(w)}
          >
            近 {w} 天
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading-spinner">
          <div className="spinner" />
        </div>
      ) : (
        <>
          <div className="usage-cards">
            <div className="usage-card">
              <div className="usage-card__value">{fmt(stats?.input_tokens ?? 0)}</div>
              <div className="usage-card__label small muted">输入 tokens · 近 {days} 天</div>
            </div>
            <div className="usage-card">
              <div className="usage-card__value">{fmt(stats?.output_tokens ?? 0)}</div>
              <div className="usage-card__label small muted">输出 tokens · 近 {days} 天</div>
            </div>
            <div className="usage-card">
              <div className="usage-card__value">{fmt(totalCalls)}</div>
              <div className="usage-card__label small muted">调用次数 · 近 {days} 天</div>
            </div>
          </div>

          {totalCalls > 0 ? (
            <div className="usage-bar" role="img" aria-label="按模型调用占比">
              {byModel.map((m, i) => (
                <div
                  key={m.model}
                  className="usage-bar__seg"
                  title={`${m.model}:${m.calls} 次(${Math.round((m.calls / totalCalls) * 100)}%)`}
                  style={{
                    width: `${Math.max((m.calls / totalCalls) * 100, 1.5)}%`,
                    background: BAR_COLORS[i % BAR_COLORS.length],
                  }}
                />
              ))}
            </div>
          ) : null}

          {byModel.length === 0 ? (
            <p className="muted small">
              还没有用量:与 agent 对话或让 agent 执行任务后,计量会自动累计。
            </p>
          ) : (
            <table className="usage-table">
              <thead>
                <tr>
                  <th>模型</th>
                  <th>输入 tokens</th>
                  <th>输出 tokens</th>
                  <th>调用次数</th>
                </tr>
              </thead>
              <tbody>
                {byModel.map((m, i) => (
                  <tr key={m.model}>
                    <td className="mono">
                      <span
                        className="usage-table__dot"
                        style={{ background: BAR_COLORS[i % BAR_COLORS.length] }}
                      />
                      {m.model}
                    </td>
                    <td>{m.input}</td>
                    <td>{m.output}</td>
                    <td>{m.calls}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
  );
}
