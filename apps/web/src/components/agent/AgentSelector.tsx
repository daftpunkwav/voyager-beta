import type { AgentProfile } from '@/api/types';
import { useAgentStore } from '@/stores/agentStore';
import { AGENT_INITIALS, AGENT_ROLE_LABELS } from '@/utils/labels';

interface AgentSelectorProps {
  profiles: AgentProfile[];
}

/**
 * Hub 调度状态条（不可手动切换 Agent）。
 * 展示当前生效 Agent，由 Hub 根据意图智能调度；保留 profiles 接口便于未来扩展。
 */
export function AgentSelector({ profiles }: AgentSelectorProps) {
  const activeAgent = useAgentStore((s) => s.activeAgent);
  const hubProfile = profiles.find((p) => p.id === 'hub');
  const activeProfile = profiles.find((p) => p.id === activeAgent) ?? hubProfile;

  return (
    <div className="agent-switcher agent-switcher--hub-only" title="由 Hub 智能调度，无需手动选择">
      <div className={`agent-avatar agent-hub ${activeAgent === 'hub' ? 'active' : ''}`} title="Hub · 总调度">
        <span>{AGENT_INITIALS.hub ?? 'H'}</span>
      </div>
      {activeAgent !== 'hub' && (
        <>
          <span className="agent-switcher__arrow" aria-hidden>
            →
          </span>
          <div
            className={`agent-avatar agent-${activeAgent} active`}
            title={`${activeProfile?.name ?? activeAgent} · Hub 已调度`}
          >
            <span>{AGENT_INITIALS[activeAgent] ?? activeProfile?.name?.[0] ?? '?'}</span>
          </div>
        </>
      )}
      <div className="agent-switcher__meta">
        <span className="agent-switcher__label">
          {activeAgent === 'hub'
            ? 'Hub 调度中'
            : `Hub → ${activeProfile?.name ?? activeAgent}`}
        </span>
        <span className="agent-switcher__hint">
          {AGENT_ROLE_LABELS[activeAgent] ?? activeProfile?.description ?? '智能路由'}
        </span>
      </div>
    </div>
  );
}
