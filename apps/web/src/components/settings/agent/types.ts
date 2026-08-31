/** Agent 设置各块共享的微小类型;不要造巨大 types.ts */

export interface SettingItem<T = string> {
  value?: T;
  default?: T;
}

export interface ProfileItem {
  key: string;
  value: unknown;
}

export interface EpisodicEntry {
  id: number;
  ts: number;
  kind: string;
  summary: string;
}

export interface SemanticFact {
  id: number;
  ts: number;
  subject: string;
  relation: string;
  object: string;
}

export interface MemorySnapshot {
  profile: { summary: string; items: ProfileItem[] };
  episodic: { recent: EpisodicEntry[]; shown: number };
  semantic: { recent: SemanticFact[]; shown: number };
  working: { size: number };
  retention_days: number;
  purged_episodic: number;
}

export type MemoryZone = 'profile' | 'episodic' | 'semantic' | 'working' | 'all';

export interface SkillItem {
  name: string;
  description: string;
}

export interface McpToolPreview {
  name: string;
  description: string;
}

export interface McpServerState {
  id: string;
  name: string;
  kind: 'stdio' | 'url';
  command: string;
  args: string[];
  url: string;
  approval: 'package' | 'item';
  approved: string[];
  enabled: boolean;
  connected: boolean;
  error: string;
  preview: McpToolPreview[];
  mounted: string[];
}

export interface McpAddResult {
  ok: boolean;
  id: string;
  connected: boolean;
  error: string;
  preview: McpToolPreview[];
}

export interface McpApproveResult {
  ok: boolean;
  approved: string[];
  mounted: string[];
}

export interface McpFormDraft {
  id: string;
  name: string;
  kind: 'stdio' | 'url';
  command: string;
  argsDraft: string;
  url: string;
  approval: 'package' | 'item';
}
