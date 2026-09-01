import { AGENT_CATALOG } from '@/constants/agentCatalog';

export const CONDUCT_MAX = 4000;
export const GUIDELINE_MAX = 2000;

/** 通用行为准则(agent.conduct,§9.14):用户写的全局规则,注入每次对话 system */
export const CONDUCT_KEY = 'agent.conduct';
/** 分 Agent 行为准则(agent.guidelines,§9.14):{ <人格结构ID>: 文本 },叠加在通用准则上 */
export const GUIDELINES_KEY = 'agent.guidelines';

/** 全局说话风格预设(agent.style,自由字符串的常用取值;叠加在每个人格气质之上) */
export const STYLE_PRESETS = ['热心', '毒舌', '严谨', '简洁', '幽默', '专业'];
export const STYLE_KEY = 'agent.style';

/** 情节记忆保留天数(agent.memory.retention_days;范围与 SettingDef 一致) */
export const RETENTION_KEY = 'agent.memory.retention_days';
export const RETENTION_MAX = 3650;

/** 轮数上限(agent.rounds.*;范围与 SettingDef 一致) */
export const ROUNDS_MAX_KEY = 'agent.rounds.max';
export const ROUNDS_TOOL_KEY = 'agent.rounds.tool_max';
export const ROUNDS_RE_MAX = 200;
export const ROUNDS_TOOL_MAX = 500;

/** 网络权限(agent.network.*;档位值与后端枚举一致) */
export const NETWORK_MODE_KEY = 'agent.network.mode';
export const NETWORK_DOMAINS_KEY = 'agent.network.domains';
export const NETWORK_MODE_OPTIONS = [
  { value: 'off', label: '关闭' },
  { value: 'whitelist', label: '白名单' },
  { value: 'all', label: '全开' },
];

/** 工作目录(agent.workspace.dir,§9.10):相对仓库根,保存后需重启才换 jail */
export const WORKDIR_KEY = 'agent.workspace.dir';

/** 附加只读根(agent.fs.read_roots,§9.9/phase-53):绝对路径列表,读可访问,写/删仍仅限工作目录 */
export const READ_ROOTS_KEY = 'agent.fs.read_roots';

/** 附加读写根(agent.fs.write_roots,§9.9/phase-55):绝对路径列表,读 L0,写/删须 L2 确认,仍受 workspace 优先 */
export const WRITE_ROOTS_KEY = 'agent.fs.write_roots';

/** 主动触达预算(agent.proactive.*,§9.8/phase-18):范围与 SettingDef 一致 */
export const PROACTIVE_PER_SESSION_KEY = 'agent.proactive.per_session';
export const PROACTIVE_PER_SESSION_MAX = 20;
export const PROACTIVE_PER_DAY_KEY = 'agent.proactive.per_day';
export const PROACTIVE_PER_DAY_MAX = 100;
export const PROACTIVE_FOLLOW_UP_MAX_KEY = 'agent.proactive.follow_up_max';
export const PROACTIVE_FOLLOW_UP_MAX = 5;
export const PROACTIVE_QUIET_START_KEY = 'agent.proactive.quiet_start';
export const PROACTIVE_QUIET_START_MAX = 23;
export const PROACTIVE_QUIET_END_KEY = 'agent.proactive.quiet_end';
export const PROACTIVE_QUIET_END_MAX = 23;

/** 观察自动行动(agent.observe.auto_index,§9.2/phase-12):默认关,只提示不建索引 */
export const AUTO_INDEX_KEY = 'agent.observe.auto_index';

/** 应用内能力白名单(agent.app.*,§9.9/phase-19):仅用户可改,热读后影响桥工具 */
export const APP_ALLOWED_KEY = 'agent.app.allowed';
export const APP_DENIED_KEY = 'agent.app.denied';

/** 记忆区中文名(确认框标题与 toast 用) */
export const ZONE_LABELS: Record<'profile' | 'episodic' | 'semantic' | 'working' | 'all', string> = {
  profile: '用户画像',
  episodic: '情节记忆',
  semantic: '语义记忆',
  working: '工作记忆',
  all: '全部记忆',
};

/** 分区清空确认文案:写清"对话时间线/笔记/项目保留" */
export const CONFIRM_MESSAGES: Record<'all' | 'profile' | 'episodic' | 'semantic', string> = {
  all: '确定清空 Agent 的全部记忆（用户画像、情节、语义、工作）？对话时间线、笔记与项目会保留，此操作不可恢复。',
  profile: '确定清空用户画像？Agent 将忘记你的偏好与背景。对话时间线、笔记与项目会保留，此操作不可恢复。',
  episodic: '确定清空情节记忆（决策与事件留痕）？对话时间线、笔记与项目会保留，此操作不可恢复。',
  semantic: '确定清空语义记忆（事实三元组）？对话时间线、笔记与项目会保留，此操作不可恢复。',
};

export const EMPTY_MCP_FORM = {
  id: '',
  name: '',
  kind: 'stdio' as const,
  command: '',
  argsDraft: '',
  url: '',
  approval: 'package' as const,
};

/** get_setting 值转数字输入草稿;非数字(如 mock/异常值)回落空串,避免 NaN 挂草稿 */
export const numericDraft = (item: { value?: number; default?: number }) => {
  const n = Number(item.value ?? item.default);
  return Number.isFinite(n) ? String(n) : '';
};

/** 情节 ts 是 unix 秒,转本地时间展示 */
export const fmtTs = (ts: number) => new Date(ts * 1000).toLocaleString();

/** 画像值非字符串(数字/对象)时以 JSON 展示,避免 "[object Object]" */
export const fmtValue = (value: unknown) =>
  typeof value === 'string' ? value : JSON.stringify(value) ?? '';

export const DEFAULT_AGENT_ID = AGENT_CATALOG[0]?.id ?? 'orchestrator';
