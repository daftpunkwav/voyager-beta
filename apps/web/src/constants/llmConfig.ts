// @ts-nocheck — 迁移期:RepoPilot 风格代码,新 page / hook 仍按 strict 写(见各文件顶部注释)。
import type { AgentLlmConfig, AgentSpeakingStyle, LlmApiFormat } from '@/api/types';
import { AGENT_CATALOG } from '@/constants/agentCatalog';

/** LLM API 兼容格式 */
export const LLM_API_FORMAT_OPTIONS: { value: LlmApiFormat; label: string; hint: string }[] = [
  { value: 'openai', label: 'OpenAI 兼容', hint: '/v1/chat/completions' },
  { value: 'anthropic', label: 'Anthropic 兼容', hint: '/v1/messages' },
  { value: 'google', label: 'Google Gemini', hint: 'generateContent' },
  { value: 'ollama', label: 'Ollama 本地', hint: '/api/chat' },
  { value: 'custom', label: '自定义', hint: '由后端按 api_format 路由' },
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

/** 内置供应商预设 — 选择后自动填充 base URL / 格式 / 模型列表 */
export interface LlmProviderPreset {
  id: string;
  display_name: string;
  default_base_url: string;
  api_format: LlmApiFormat;
  available_models: string[];
  default_model: string;
}

export const LLM_PROVIDER_PRESETS: LlmProviderPreset[] = [
  {
    id: 'openai',
    display_name: 'OpenAI',
    default_base_url: 'https://api.openai.com/v1',
    api_format: 'openai',
    available_models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4.1', 'o3-mini'],
    default_model: 'gpt-4o',
  },
  {
    id: 'anthropic',
    display_name: 'Anthropic',
    default_base_url: 'https://api.anthropic.com',
    api_format: 'anthropic',
    available_models: ['claude-sonnet-4-6', 'claude-opus-4-6', 'claude-haiku-4-5'],
    default_model: 'claude-sonnet-4-6',
  },
  {
    id: 'google',
    display_name: 'Google AI',
    default_base_url: 'https://generativelanguage.googleapis.com/v1beta',
    api_format: 'google',
    available_models: ['gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-2.0-flash'],
    default_model: 'gemini-2.5-flash',
  },
  {
    id: 'zhipu',
    display_name: '智谱 AI (GLM)',
    default_base_url: 'https://open.bigmodel.cn/api/paas/v4',
    api_format: 'openai',
    available_models: ['glm-5.2', 'glm-5.1', 'glm-4-plus', 'glm-4-flash'],
    default_model: 'glm-5.2',
  },
  {
    id: 'deepseek',
    display_name: 'DeepSeek',
    default_base_url: 'https://api.deepseek.com/v1',
    api_format: 'openai',
    available_models: ['deepseek-chat', 'deepseek-reasoner'],
    default_model: 'deepseek-chat',
  },
  {
    id: 'minimax',
    display_name: 'MiniMax',
    default_base_url: 'https://api.minimaxi.com/anthropic',
    api_format: 'anthropic',
    available_models: [
      'MiniMax-M3',
      'MiniMax-M2.7',
      'MiniMax-M2.7-highspeed',
      'MiniMax-M2.5',
    ],
    default_model: 'MiniMax-M2.7',
  },
  {
    id: 'ollama',
    display_name: 'Ollama（本地）',
    default_base_url: 'http://127.0.0.1:11434',
    api_format: 'ollama',
    available_models: ['llama3.3', 'qwen2.5', 'deepseek-r1'],
    default_model: 'llama3.3',
  },
  {
    id: 'custom',
    display_name: '自定义供应商',
    default_base_url: '',
    api_format: 'custom',
    available_models: [],
    default_model: '',
  },
];

export function findProviderPreset(id: string): LlmProviderPreset | undefined {
  return LLM_PROVIDER_PRESETS.find((p) => p.id === id);
}

/** 新建供应商草稿（本地 id，保存时由后端保留） */
export function createProviderFromPreset(presetId: string): {
  id: string;
  preset_id: string;
  display_name: string;
  enabled: boolean;
  api_base: string | null;
  api_format: LlmApiFormat;
  available_models: string[];
  default_model: string;
  configured: boolean;
  api_key_masked: string | null;
} {
  const preset = findProviderPreset(presetId) ?? findProviderPreset('custom') ?? LLM_PROVIDER_PRESETS[0];
  if (!preset) {
    throw new Error('内置 custom 供应商预设缺失');
  }
  return {
    id: crypto.randomUUID(),
    preset_id: preset.id,
    display_name: preset.display_name,
    enabled: true,
    api_base: preset.default_base_url || null,
    api_format: preset.api_format,
    available_models: [...preset.available_models],
    default_model: preset.default_model,
    configured: false,
    api_key_masked: null,
  };
}

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
