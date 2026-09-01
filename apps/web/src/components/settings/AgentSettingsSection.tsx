import { AppPolicyBlock } from './agent/AppPolicyBlock';
import { ConductBlock } from './agent/ConductBlock';
import { GuidelinesBlock } from './agent/GuidelinesBlock';
import { McpBlock } from './agent/McpBlock';
import { MemoryBlock } from './agent/MemoryBlock';
import { MemoryRetentionBlock } from './agent/MemoryRetentionBlock';
import { NetworkBlock } from './agent/NetworkBlock';
import { ObserveBlock } from './agent/ObserveBlock';
import { ProactiveBlock } from './agent/ProactiveBlock';
import { ReadRootsBlock } from './agent/ReadRootsBlock';
import { RoundsBlock } from './agent/RoundsBlock';
import { SkillsBlock } from './agent/SkillsBlock';
import { StyleBlock } from './agent/StyleBlock';
import { TokenQuotaBlock } from './agent/TokenQuotaBlock';
import { WorkspaceBlock } from './agent/WorkspaceBlock';
import { WriteRootsBlock } from './agent/WriteRootsBlock';

/** 设置 → Agent:按块组装的壳;各块自己持 state、自己拉数据、自己 toast。 */
export function AgentSettingsSection() {
  return (
    <section className="settings-section glass-card glass-card--overview-outer">
      <h2>Agent</h2>
      <p className="section-desc">行为准则与记忆管理。准则会注入每次对话的系统提示，所有 Agent 必须遵守。</p>

      <ConductBlock />
      <StyleBlock />
      <GuidelinesBlock />
      <RoundsBlock />
      <TokenQuotaBlock />
      <NetworkBlock />
      <WorkspaceBlock />
      <ReadRootsBlock />
      <WriteRootsBlock />
      <AppPolicyBlock />
      <ProactiveBlock />
      <ObserveBlock />
      <SkillsBlock />
      <McpBlock />
      <MemoryBlock />
      <MemoryRetentionBlock />
    </section>
  );
}
