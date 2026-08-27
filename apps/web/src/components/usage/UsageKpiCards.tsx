// @ts-nocheck — 待后端契约确认:UsageKpiCards.tsx:12 页面读 usage.totals.total_tokens/prompt_cached_tokens/top,后端 get_usage_stats 均不提供(services/llm/store.py),边界归一需臆造数据;其余错误已清
import type { LlmUsageSummary } from '@/api/types';
import { GLASS_CHIP } from '@/constants/glassTokens';
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
