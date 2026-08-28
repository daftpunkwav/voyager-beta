/**
 * 人格结构 ID(职责)与历史别名。显示名在 AGENT_CATALOG / 后端 personas 数据层。
 */

export const PERSONA_IDS = [
  'orchestrator',
  'recon',
  'explainer',
  'organizer',
  'graph_guide',
] as const;

export type PersonaDutyId = (typeof PERSONA_IDS)[number];

const ALIASES: Record<string, PersonaDutyId> = {
  orchestrator: 'orchestrator',
  lucien: 'orchestrator',
  hub: 'orchestrator',
  recon: 'recon',
  iris: 'recon',
  scout: 'recon',
  navigator: 'recon',
  explainer: 'explainer',
  elio: 'explainer',
  mentor: 'explainer',
  organizer: 'organizer',
  miyai: 'organizer',
  curator: 'organizer',
  scribe: 'organizer',
  graph_guide: 'graph_guide',
  atlas: 'graph_guide',
};

export function canonicalPersonaId(id: string | null | undefined): string {
  if (!id) return 'orchestrator';
  // 未知 ID 原样返回(自建 subagent);勿收成 orchestrator,否则 SSE 切人会串到 Lucien
  return ALIASES[id] ?? id;
}

export function isOrchestrator(id: string | null | undefined): boolean {
  return canonicalPersonaId(id) === 'orchestrator';
}

export function personaCssClass(id: string | null | undefined): string {
  return `agent-${canonicalPersonaId(id)}`;
}

/** 结构 ID / 历史别名 → 显示名(数据层)。 */
export const PERSONA_DISPLAY_NAME: Record<string, string> = {
  orchestrator: 'Lucien',
  hub: 'Lucien',
  lucien: 'Lucien',
  recon: 'Iris',
  scout: 'Iris',
  navigator: 'Iris',
  iris: 'Iris',
  explainer: 'Elio',
  mentor: 'Elio',
  elio: 'Elio',
  organizer: 'Miyai',
  curator: 'Miyai',
  scribe: 'Miyai',
  miyai: 'Miyai',
  graph_guide: 'Atlas',
  atlas: 'Atlas',
};

export function personaDisplayName(id: string | null | undefined): string {
  if (!id) return PERSONA_DISPLAY_NAME.orchestrator;
  return PERSONA_DISPLAY_NAME[id] ?? PERSONA_DISPLAY_NAME[canonicalPersonaId(id)] ?? id;
}
