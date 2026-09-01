import { useQuery } from '@tanstack/react-query';
import { callCapability } from '@/bridge/client';
import { BACKEND_UNREACHABLE, extractErrorMessage } from '@/utils/errors';
import { GLASS_CHIP } from '@/constants/glassTokens';
import { formatTokenCount, formatTokenPercent } from '@/utils/formatTokens';

interface DailyQuota {
  tokens_used_today: number;
  daily_tokens: number;
}

/** 接近上限的告警阈值：达到 90% 视为「接近 100%」，进度条转 warning 色 */
const WARNING_RATIO = 0.9;

/** 今日 token 配额块(§9.9 资源维)：读 agent 进程内 Meter 的当日用量，
 *  UTC 自然日切日、输入+输出合计；与下方 llm 持久化的「最近 N 天」历史统计口径不同。
 *  daily_tokens = 0 表示不限，不画假进度条。 */
export function DailyTokenQuotaCard() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['agent-daily-quota'],
    queryFn: () => callCapability<DailyQuota>('agent', 'get_resource_quota', {}),
  });

  const used = data?.tokens_used_today ?? 0;
  const limit = data?.daily_tokens ?? 0;
  const limited = limit > 0;
  const pct = limited ? Math.min(100, (used / limit) * 100) : 0;
  const isWarning = limited && used / limit >= WARNING_RATIO;

  return (
    <div className={`${GLASS_CHIP} usage-panel usage-quota`}>
      <div className="usage-quota-head">
        <h3 className="usage-panel-title">今日 token 配额</h3>
        <span className="usage-quota-value" aria-label="今日已用 token">
          {/* 数据未到时显示占位：limit 默认 0 会误显示「不限」 */}
          {isLoading ? (
            '—'
          ) : (
            <>
              已用 {formatTokenCount(used)}
              <span className="usage-quota-sep">·</span>
              上限 {limited ? formatTokenCount(limit) : '不限'}
            </>
          )}
        </span>
      </div>

      {isLoading && <p className="muted usage-quota-note">读取中…</p>}

      {isError && (
        <div className="usage-quota-error">
          <span className="muted usage-quota-note">
            配额读取失败：{extractErrorMessage(error) || BACKEND_UNREACHABLE}
          </span>
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => void refetch()}>
            重试
          </button>
        </div>
      )}

      {!isLoading && !isError && (
        <>
          {limited ? (
            <div
              className={`usage-quota-bar${isWarning ? ' is-warning' : ''}`}
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(pct)}
              aria-label="今日 token 配额使用进度"
            >
              <div className="usage-quota-bar-fill" style={{ width: `${pct}%` }} />
            </div>
          ) : null}
          <p className="muted usage-quota-note">
            {limited
              ? `剩余 ${formatTokenCount(Math.max(0, limit - used))} · ${formatTokenPercent(used, limit)}`
              : '未设上限，不计进度'}
            ；当日（UTC 自然日切日）输入 + 输出 token 合计，仅统计 agent 进程内 Meter，与下方「最近 N 天」历史用量口径不同。
          </p>
        </>
      )}
    </div>
  );
}
