/** 团队页状态:人格预设 + 自建 subagent + 运行实例(3s 轮询)+
 * 工具面名册 + 权限矩阵设置键。数据全经 agent 域能力(parity,§5)。
 */

import { create } from 'zustand';
import { callCapability, ServiceError } from '@/bridge/client';

export interface Persona {
  key: string;
  display_name: string;
  style: string;
  default_mode: string;
  tool_allow: string[] | null; // null = 不裁剪(白名单语义,坑 1)
  system_prompt: string;
}

export interface SubagentDef {
  name: string;
  mode: string;
  description: string;
  persona: string;
  allowed_tools: string[] | null;
}

export interface RunningInstance {
  id: string;
  name: string;
  status: string; // pending/running/waiting_input/paused/completed/failed/cancelled
  goal: string;
  started_ts: number;
}

export interface SkillItem {
  name: string;
  description: string;
}

export interface ToolItem {
  name: string;
  description: string;
}

export const MODES = ['react', 'plan_execute', 'cot', 'tot', 'got', 'reflexion', 'direct'];
export const INSTANCE_POLL_MS = 3000;

/** 权限矩阵四维的设置键(§5.3;值在设置页改,矩阵只读)。 */
export interface MatrixSettings {
  networkMode: string;
  networkDomains: string[];
  workspaceDir: string;
  roundsMax: number;
  roundsToolMax: number;
  maxConcurrent: number;
}

interface TeamState {
  personas: Persona[];
  definitions: SubagentDef[];
  running: RunningInstance[];
  skills: SkillItem[];
  tools: ToolItem[];
  matrix: MatrixSettings | null;
  loading: boolean;
  error: { code: string; message: string } | null;
  init: () => Promise<void>;
  refreshInstances: () => Promise<void>;
  register: (input: {
    name: string;
    description: string;
    mode: string;
    allowed_tools: string[] | null;
    persona: string;
  }) => Promise<void>;
}

async function loadMatrix(): Promise<MatrixSettings> {
  const keys = [
    'agent.network.mode', 'agent.network.domains', 'agent.workspace.dir',
    'agent.rounds.max', 'agent.rounds.tool_max', 'agent.subagents.max_concurrent',
  ] as const;
  const results = await Promise.all(
    keys.map((key) => callCapability<{ value: unknown }>('agent', 'get_setting', { key })),
  );
  const value = (i: number): unknown => results[i]?.value;
  return {
    networkMode: String(value(0)),
    networkDomains: Array.isArray(value(1)) ? (value(1) as unknown[]).map(String) : [],
    workspaceDir: String(value(2)),
    roundsMax: Number(value(3)),
    roundsToolMax: Number(value(4)),
    maxConcurrent: Number(value(5)),
  };
}

export const useTeamStore = create<TeamState>((set) => ({
  personas: [],
  definitions: [],
  running: [],
  skills: [],
  tools: [],
  matrix: null,
  loading: false,
  error: null,

  init: async () => {
    set({ loading: true, error: null });
    try {
      const [personas, subs, skills, tools, matrix] = await Promise.all([
        callCapability<Persona[]>('agent', 'list_personas'),
        callCapability<{ definitions: SubagentDef[]; running: RunningInstance[] }>(
          'agent', 'list_subagents',
        ),
        callCapability<SkillItem[]>('agent', 'list_skills'),
        callCapability<ToolItem[]>('agent', 'list_tools'),
        loadMatrix(),
      ]);
      set({
        personas, definitions: subs.definitions, running: subs.running,
        skills, tools, matrix, loading: false,
      });
    } catch (err) {
      const e = err as ServiceError;
      set({ loading: false, error: { code: e.code, message: e.message } });
    }
  },

  refreshInstances: async () => {
    try {
      const subs = await callCapability<{ running: RunningInstance[] }>(
        'agent', 'list_subagents',
      );
      set({ running: subs.running });
    } catch {
      // 轮询失败静默,下次再试
    }
  },

  register: async (input) => {
    await callCapability('agent', 'register_subagent', input);
    const subs = await callCapability<{ definitions: SubagentDef[] }>(
      'agent', 'list_subagents',
    );
    set({ definitions: subs.definitions });
  },
}));
