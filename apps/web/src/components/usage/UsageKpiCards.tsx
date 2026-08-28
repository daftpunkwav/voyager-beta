import type { LlmUsageSummary } from '@/api/types';
import { GLASS_CHIP } from '@/constants/glassTokens';
import { formatTokenCount, formatTokenPercent } from '@/utils/formatTokens';

interface UsageKpiCardsProps {
  usage: LlmUsageSummary;
}

function normalizeTotals(usage: LlmUsageSummary) {
  const t = usage.totals;
  if (t) {
    return {
      total_tokens: t.total_tokens ?? usage.total_input_tokens + usage.total_output_tokens,
      prompt_cached_tokens: t.prompt_cached_tokens ?? Math.round((t.input_tokens ?? usage.total_input_tokens) * 0.3),
      prompt_uncached_tokens: t.prompt_uncached_tokens ?? Math.round((t.input_tokens ?? usage.total_input_tokens) * 0.7),
      completion_tokens: t.completion_tokens ?? t.output_tokens ?? usage.total_output_tokens,
      calls: t.calls ?? 0,
    };
  }
  return {
    total_tokens: usage.total_input_tokens + usage.total_output_tokens,
    prompt_cached_tokens: Math.round(usage.total_input_tokens * 0.3),
    prompt_uncached_tokens: Math.round(usage.total_input_tokens * 0.7),
    completion_tokens: usage.total_output_tokens,
    calls: 0,
  };
}

export function UsageKpiCards({ usage }: UsageKpiCardsProps) {
  const t = normalizeTotals(usage);
  const top = usage.top;
  const topLabel =
    top?.label ||
    (top ? `${top.provider ?? 'unknown'}/${top.model}` : null) ||
    usage.by_model[0]?.label ||
    usage.by_model[0]?.model ||
    '—';
  const topTokens = top?.total_tokens ?? usage.by_model[0]?.total_tokens;
  const topShare =
    topTokens != null && t.total_tokens > 0
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
        <div key={item.label} className={`${GLASS_CHIP} usage-kpi-card`}>
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
