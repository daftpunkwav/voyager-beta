import type { AgentLlmConfig, AgentSpeakingStyle, LlmApiFormat } from '@/api/types';
import { AGENT_CATALOG } from '@/constants/agentCatalog';

/** API 格式选项(与后端 services/llm/catalog.py 对齐:仅 chat / anthropic) */
export const LLM_API_FORMAT_OPTIONS: { value: LlmApiFormat; label: string; hint: string }[] = [
  { value: 'chat', label: 'OpenAI 兼容', hint: '/v1/chat/completions' },
  { value: 'anthropic', label: 'Anthropic', hint: '/v1/messages' },
];

/** Agent 说话风格 */
export const SPEAKING_STYLE_OPTIONS: { value: AgentSpeakingStyle; label: string; desc: string }[] = [
  { value: 'default', label: '默认', desc: '平衡、中性' },
  { value: 'warm', label: '热情', desc: '鼓励式、积极' },
  { value: 'sharp', label: '毒蛇', desc: '犀利、一针见血' },
  { value: 'professional', label: '专业', desc: '严谨、少废话' },
  { value: 'humorous', label: '幽默', desc: '轻松、适当玩笑' },
  { value: 'concise', label: '简洁', desc: '短句、要点优先' },
  { value: 'mentor', label: '导师', desc: '循序渐进讲解' },
  { value: 'socratic', label: '苏格拉底', desc: '反问引导思考' },
];

/** 为全部 Agent 生成默认 LLM 配置 */
export function createDefaultAgentLlmConfigs(): AgentLlmConfig[] {
  return AGENT_CATALOG.map((a) => ({
    agent_id: a.id,
    provider_id: null,
    model_override: null,
    speaking_style: 'default' as AgentSpeakingStyle,
  }));
}

export function speakingStyleLabel(style: AgentSpeakingStyle): string {
  return SPEAKING_STYLE_OPTIONS.find((o) => o.value === style)?.label ?? style;
}
