import type { AgentProfile } from '@/api/types';
import { canonicalPersonaId, isOrchestrator, personaCssClass } from '@/constants/personas';
import { useAgentStore } from '@/stores/agentStore';
import { AGENT_INITIALS, AGENT_ROLE_LABELS } from '@/utils/labels';

interface AgentSelectorProps {
  profiles: AgentProfile[];
}

/**
 * 统筹者调度状态条（不可手动切换 Agent）。
 * 展示当前生效人格，由 orchestrator 根据意图智能调度。
 */
export function AgentSelector({ profiles }: AgentSelectorProps) {
  const activeAgent = useAgentStore((s) => s.activeAgent);
  const masterProfile = profiles.find((p) => isOrchestrator(p.id || p.key));
  const activeProfile =
    profiles.find((p) => canonicalPersonaId(p.id || p.key) === canonicalPersonaId(activeAgent)) ??
    masterProfile;
  const master = isOrchestrator(activeAgent);

  return (
    <div className="agent-switcher agent-switcher--hub-only" title="由统筹者智能调度，无需手动选择">
      <div
        className={`agent-avatar ${personaCssClass('orchestrator')} ${master ? 'active' : ''}`}
        title="Lucien · 统筹"
      >
        <span>{AGENT_INITIALS.orchestrator ?? 'L'}</span>
      </div>
      {!master && (
        <>
          <span className="agent-switcher__arrow" aria-hidden>
            →
          </span>
          <div
            className={`agent-avatar ${personaCssClass(activeAgent)} active`}
            title={`${activeProfile?.name ?? activeAgent} · 已调度`}
          >
            <span>{AGENT_INITIALS[activeAgent] ?? activeProfile?.name?.[0] ?? '?'}</span>
          </div>
        </>
      )}
      <div className="agent-switcher__meta">
        <span className="agent-switcher__label">
          {master
            ? 'Lucien 调度中'
            : `Lucien → ${activeProfile?.name ?? activeAgent}`}
        </span>
        <span className="agent-switcher__hint">
          {AGENT_ROLE_LABELS[activeAgent] ?? activeProfile?.description ?? '智能路由'}
        </span>
      </div>
    </div>
  );
}
