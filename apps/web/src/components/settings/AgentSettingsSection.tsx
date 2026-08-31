import type { Settings } from '@/api/types';
import { ConductBlock } from './agent/ConductBlock';
import { LimitsBlock } from './agent/LimitsBlock';
import { MemoryBlock } from './agent/MemoryBlock';
import { ProactiveBlock } from './agent/ProactiveBlock';
import { McpBlock } from './agent/McpBlock';
import { ObserveBlock } from './agent/ObserveBlock';
import { SkillsBlock } from './agent/SkillsBlock';

interface AgentSettingsSectionProps {
  settings: Settings;
  updateSettings: (data: Partial<Settings>) => Promise<unknown>;
}

/** 设置 → Agent:按块组装的壳;各块自己持 state、自己拉数据、自己 toast。 */
export function AgentSettingsSection({ settings, updateSettings }: AgentSettingsSectionProps) {
  return (
    <section className="settings-section glass-card glass-card--overview-outer">
      <h2>Agent</h2>
      <p className="section-desc">行为准则与记忆管理。准则会注入每次对话的系统提示，所有 Agent 必须遵守。</p>

      <ConductBlock settings={settings} updateSettings={updateSettings} />
      <LimitsBlock />
      <ProactiveBlock />
      <ObserveBlock />
      <SkillsBlock />
      <McpBlock />
      <MemoryBlock />
    </section>
  );
}
