import { useMemo } from 'react';
import type { AgentLlmConfig, AgentSpeakingStyle, LlmProvider } from '@/api/types';
import { GlassSelect } from '@/components/common/GlassSelect';
import { AGENT_CATALOG } from '@/constants/agentCatalog';
import { SPEAKING_STYLE_OPTIONS } from '@/constants/llmConfig';
import { useSettings } from '@/hooks/useSettings';

interface LlmAgentOverridesProps {
  /** llm 服务真相的提供商列表(list_providers) */
  providers: LlmProvider[];
  /** 设置项 llm.default_provider 当前值 */
  defaultProviderId: string;
}

/** Agent 供应商与风格覆盖表:提供商下拉数据源是 llm.* 真相;
 *  每-agent 覆盖配置仍存 settings blob 的 agent_llm_configs(属设置服务契约,
 *  本阶段不迁移;Blob 通道现状在 phase 写回中单独说明)。 */
export function LlmAgentOverrides({
  providers,
  defaultProviderId,
}: LlmAgentOverridesProps) {
  const { settings, updateSettings } = useSettings();

  const agentConfigsMap = useMemo(() => {
    const m = new Map<string, AgentLlmConfig>();
    for (const c of settings?.agent_llm_configs ?? []) m.set(c.agent_id, c);
    return m;
  }, [settings?.agent_llm_configs]);

  const enabledProviders = providers.filter((p) => p.enabled);
  const defaultProvider =
    providers.find((p) => p.id === defaultProviderId) ?? enabledProviders[0];

  const updateAgentConfig = (agentId: string, patch: Partial<AgentLlmConfig>) => {
    const next = AGENT_CATALOG.map((a) => {
      const existing = agentConfigsMap.get(a.id) ?? {
        agent_id: a.id,
        provider_id: null,
        model_override: null,
        speaking_style: 'default' as AgentSpeakingStyle,
      };
      return a.id === agentId ? { ...existing, ...patch } : existing;
    });
    void updateSettings({ agent_llm_configs: next });
  };

  return (
    <div className="llm-settings-block glass-card glass-card--overview-inner glass-overflow-visible">
      <h3 className="llm-block-title">Agent 供应商与风格</h3>
      <p className="llm-block-desc">
        每个 Agent 可指定供应商与模型；留空则使用默认供应商的默认模型
      </p>

      <div className="llm-agent-table-wrap">
        <table className="llm-agent-table">
          <thead>
            <tr>
              <th>Agent</th>
              <th>供应商</th>
              <th>模型</th>
              <th>说话风格</th>
            </tr>
          </thead>
          <tbody>
            {AGENT_CATALOG.map((agent) => {
              const cfg = agentConfigsMap.get(agent.id) ?? {
                agent_id: agent.id,
                provider_id: null,
                model_override: null,
                speaking_style: 'default' as AgentSpeakingStyle,
              };
              const provider =
                enabledProviders.find((p) => p.id === cfg.provider_id) ?? defaultProvider;
              const modelOptions = provider?.models?.length
                ? provider.models
                : ([provider?.default_model].filter(Boolean) as string[]);

              return (
                <tr key={agent.id}>
                  <td>
                    <div className="llm-agent-cell">
                      <span
                        className="llm-agent-avatar"
                        style={{ background: agent.color }}
                        aria-hidden
                      >
                        {agent.name[0]}
                      </span>
                      <div>
                        <div className="llm-agent-name">{agent.name}</div>
                        <div className="llm-agent-tagline muted">{agent.tagline}</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <GlassSelect
                      size="sm"
                      value={cfg.provider_id ?? ''}
                      options={[
                        {
                          value: '',
                          label: `默认（${defaultProvider?.display_name ?? '—'}）`,
                        },
                        ...enabledProviders.map((p) => ({
                          value: p.id,
                          label: p.display_name,
                        })),
                      ]}
                      onChange={(v) =>
                        updateAgentConfig(agent.id, {
                          provider_id: v || null,
                          // 切换供应商时清空模型覆盖，避免指向不存在的模型
                          model_override: null,
                        })
                      }
                      aria-label={`${agent.name} 供应商`}
                    />
                  </td>
                  <td>
                    <GlassSelect
                      size="sm"
                      value={cfg.model_override ?? ''}
                      options={[
                        {
                          value: '',
                          label: `使用默认（${provider?.default_model || '—'}）`,
                        },
                        ...modelOptions.map((m) => ({ value: m, label: m })),
                      ]}
                      onChange={(v) =>
                        updateAgentConfig(agent.id, { model_override: v || null })
                      }
                      aria-label={`${agent.name} 模型`}
                    />
                  </td>
                  <td>
                    <GlassSelect
                      size="sm"
                      value={cfg.speaking_style}
                      options={SPEAKING_STYLE_OPTIONS.map((opt) => ({
                        value: opt.value,
                        label: `${opt.label} — ${opt.desc}`,
                      }))}
                      onChange={(v) =>
                        updateAgentConfig(agent.id, {
                          speaking_style: v as AgentSpeakingStyle,
                        })
                      }
                      aria-label={`${agent.name} 说话风格`}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
