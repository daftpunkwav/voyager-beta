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

export interface PluginPermissions {
  scopes: string[];
  network: string;
  fs: string;
}

/** list_plugins 每项的明细条目(phase-74) */
export interface PluginSkillDetail {
  name: string;
  approved: boolean;
}

export interface PluginHookDetail {
  path: string; // 相对插件目录;分项勾选/装载按它
  on: string;
  enabled: boolean;
  approved: boolean;
}

export interface PluginMcpDetail {
  id: string;
  approved: boolean; // 插件分项是否勾选这台
  registered: boolean; // 是否已在「外接 MCP」登记(待批准)
  tools_approved: string[]; // 既有 MCP 存储的已批准工具(只读;空 = 未批准工具)
}

export interface PluginItem {
  name: string;
  version: string;
  description: string;
  approved: boolean;
  granularity: '' | 'bundle' | 'item'; // 已批准时的装载粒度(phase-74)
  permissions: PluginPermissions;
  contains: { skills: number; hooks: number; mcp: boolean };
  skills: PluginSkillDetail[];
  hooks: PluginHookDetail[];
  mcp: PluginMcpDetail[];
  path: string;
}

export interface PluginApproveResult {
  name: string;
  approved: boolean;
  loaded: { skills: string[]; hooks: number; mcp_registered: number; mcp_skipped: boolean };
  granularity?: 'bundle' | 'item';
  skipped?: { skills: string[]; hooks: string[]; mcp: string[] };
  /** phase-76:撤销 / 改勾时按安全规则被回收的外接 MCP server id */
  mcp_reclaimed?: string[];
  /** phase-76:未回收的外接 MCP 及原因(工具已批准 / 他插件仍用 / 配置不符等) */
  mcp_reclaim_skipped?: { id: string; reason: string }[];
}

/** install_plugin 回包(phase-77):安装成功但未批准,批准仍走 set_plugin_approval */
export interface PluginInstallResult {
  name: string;
  version: string;
  path: string;
  permissions: PluginPermissions;
  contains_summary: { skills: number; hooks: number; mcp: boolean };
}
