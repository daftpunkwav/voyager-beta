/** 团队页表单常量。 */

/** 名称规则与后端 SubagentDef 同一道正则(agent/subagent/registry.py),前端先拦一道 */
export const NAME_RE = /^[a-z][a-z0-9_]*$/;

/** 执行模式七值(agent/subagent/modes.py);提交值仍是后端枚举 */
export const MODE_OPTIONS = [
  { value: 'react', label: 'ReAct' },
  { value: 'plan_execute', label: '计划执行' },
  { value: 'cot', label: '思维链' },
  { value: 'tot', label: '思维树' },
  { value: 'got', label: '思维图' },
  { value: 'reflexion', label: '反思' },
  { value: 'direct', label: '直答' },
];

export const MODE_LABELS: Record<string, string> = Object.fromEntries(
  MODE_OPTIONS.map((o) => [o.value, o.label]),
);

/** 网络档位(phase-10):'' = 跟随全局;档位值与后端 agent.network.mode 一致 */
export const NETWORK_OPTIONS = [
  { value: '', label: '跟随全局' },
  { value: 'off', label: '关闭' },
  { value: 'whitelist', label: '白名单' },
  { value: 'all', label: '全开' },
];

export const NETWORK_LABELS: Record<string, string> = Object.fromEntries(
  NETWORK_OPTIONS.map((o) => [o.value, o.label]),
);
