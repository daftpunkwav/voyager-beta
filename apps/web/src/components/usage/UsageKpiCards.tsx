import type { LlmUsageSummary } from '@/api/types';
import { USAGE_CHIP_GLASS } from '@/constants/usageGlass';
import { formatTokenCount, formatTokenPercent } from '@/utils/formatTokens';

interface UsageKpiCardsProps {
  usage: LlmUsageSummary;
}

export function UsageKpiCards({ usage }: UsageKpiCardsProps) {
  const t = usage.totals;
  const top = usage.top;
  const topLabel =
    top?.label ||
    (top ? `${top.provider}/${top.model}` : null) ||
    usage.by_model[0]?.label ||
    usage.by_model[0]?.model ||
    '—';
  const topTokens = top?.total_tokens ?? usage.by_model[0]?.total_tokens;
  const topShare =
    topTokens != null
      ? `占比 ${formatTokenPercent(topTokens, t.total_tokens)}`
      : undefined;

  const items = [
    { label: 'tokens 用量', value: formatTokenCount(t.total_tokens) },
    { label: '输入命中', value: formatTokenCount(t.prompt_cached_tokens) },
    { label: '输入未命中', value: formatTokenCount(t.prompt_uncached_tokens) },
    { label: '输出', value: formatTokenCount(t.completion_tokens) },
    { label: '调用次数', value: String(t.calls) },
    {
      label: '最常用模型',
      value: topLabel,
      sub: topShare,
    },
  ];

  return (
    <div className="usage-kpi-grid">
      {items.map((item) => (
        <div key={item.label} className={`${USAGE_CHIP_GLASS} usage-kpi-card`}>
          <div className="usage-kpi-label">{item.label}</div>
          <div className="usage-kpi-value" title={item.value}>
            {item.value}
          </div>
          {item.sub ? <div className="usage-kpi-sub">{item.sub}</div> : null}
        </div>
      ))}
    </div>
  );
}
