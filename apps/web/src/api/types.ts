/**
 * Web API / 领域类型。
 *
 * - 与后端契约对齐的类型：从 `types` 再导出（OpenAPI 权威源）
 * - 前端专属（SSE、反问 UI、图谱可视化等）：本文件定义
 */
export type {
  paths,
  components,
  operations,
  Schemas,
  ApiResponse,
  ApiError,
  PaginatedList,
  User,
  UserProfile,
  UserProfileUpdate,
  LearnerIdentity,
  LearnerIdentityUpdate,
  GithubAccount,
  GitHubAccount,
  StarRepo,
  StarsList,
  ImportResult,
  ImportRepoItem,
  Project,
  ProjectCreate,
  ProjectUpdate,
  ProjectReadme,
  ProjectStats,
  ProjectProgress,
  ProjectSource,
  Category,
  CategoryCreate,
  CategoryUpdate,
  Tag,
  TagCreate,
  Note,
  NoteCreate,
  NoteUpdate,
  ActivityItem,
  TrendingRepo,
  TrendingScoutBody,
  RecommendedProject,
  OverviewRecentNote,
  AgentSession,
  AgentSessionDetail,
  AgentMessageOut,
  AgentProfile,
  AgentPermissions,
  AgentPermissionsUpdate,
  AgentLlmConfig,
  AgentGuideline,
  AgentChatBody,
  AgentChatRequest,
  AgentQuestionAnswer,
  Settings,
  SettingsUpdate,
  LlmProviderConfig,
  LlmUsageSummary,
  LlmTokenBreakdown,
  MemoryItem,
  MemoryProposal,
  ContextWindowSegment,
  ContextWindowStats,
  Goal,
  LlmTestResult,
  ProgressUpdate,
  SetProjectTagsBody,
  SetProjectTagsResult,
} from 'types';

/** @deprecated 请优先用 ProjectCreate */
export type { ProjectCreate as CreateProjectInput } from 'types';

/** Stars 列表查询结果（别名） */
export type { StarsList as StarsListResult } from 'types';

// ========================================
// 前端查询参数 / 图谱 / Agent UI（OpenAPI 未建模或需收紧）
// ========================================

import type { ProjectProgress } from 'types';

export interface ProjectListParams {
  search?: string;
  category_id?: string;
  language?: string;
  progress?: ProjectProgress;
  tag_id?: string;
  sort_by?: 'name' | 'stars' | 'imported_at' | 'updated_at';
  sort_order?: 'asc' | 'desc';
  page?: number;
  page_size?: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphNode {
  id: string;
  name: string;
  language?: string | null;
  stars: number;
  category_id?: string | null;
  progress?: ProjectProgress;
  /** 域内基础度 0..1（启发式；可被 LLM 覆盖） */
  foundation_score?: number;
  /** 全局枢纽度 0..1（径向布局用） */
  hubness?: number;
  /** 领域社区 id */
  cluster_id?: string | null;
  cluster_size?: number;
  description?: string | null;
}

export interface GraphEdge {
  source: string;
  target: string;
  similarity: number;
  relation?: string;
  reasons?: string[];
  edge_type?: string;
}

export type TrendingPeriod = 'daily' | 'weekly' | 'monthly';

export interface TrendingScoutIntroParams {
  owner: string;
  repo: string;
  period?: TrendingPeriod;
}

export type AgentId =
  | 'hub'
  | 'scout'
  | 'mentor'
  | 'navigator'
  | 'curator'
  | 'scribe'
  | 'atlas';

export type MessageRole = 'user' | 'assistant' | 'tool' | 'system';

/** 前端气泡消息（比 AgentMessageOut 更结构化） */
export interface AgentMessage {
  id: string;
  session_id: string;
  agent: AgentId;
  role: MessageRole;
  content?: string;
  thinking?: string;
  tool_call?: ToolCallData;
  tool_calls?: ToolCallData[];
  subagents?: Array<{
    agentId: AgentId;
    task?: string;
    reason?: string;
    status: 'running' | 'ok' | 'question' | 'error';
    thinking?: string;
    output?: string;
  }>;
  question?: AgentQuestion;
  question_answer?: QuestionAnswerRecord;
  agent_switch?: {
    from: string;
    to: string;
    reason?: string;
  };
  created_at: string;
}

export interface ToolCallData {
  name: string;
  args: Record<string, unknown>;
  result?: unknown;
}

// ========================================
// 反问系统（前端交互模型）
// ========================================

export interface AgentQuestion {
  question_id: string;
  intro: { type: 'markdown'; content: string };
  questions: QuestionItem[];
  actions: {
    submit: { text: string; style: 'primary' | 'secondary' | 'ghost' | 'danger' | 'link' };
    skip?: { text: string; style: 'ghost' };
  };
  allow_skip: boolean;
  timeout: number | null;
}

export type QuestionItem =
  | RadioQuestion
  | CheckboxQuestion
  | SliderQuestion
  | DragSortQuestion
  | KnowledgeMapQuestion;

export interface RadioQuestion {
  id: string;
  text: string;
  type: 'radio';
  options: RadioOption[];
  allow_other?: boolean;
  exam?: boolean;
}

export interface RadioOption {
  value: string;
  label: string;
  description?: string;
}

export interface CheckboxQuestion {
  id: string;
  text: string;
  type: 'checkbox';
  options: CheckboxOption[];
}

export interface CheckboxOption {
  value: string;
  text: string;
}

export interface SliderQuestion {
  id: string;
  text: string;
  type: 'slider';
  min: number;
  max: number;
  labels?: Record<string, string>;
}

export interface DragSortQuestion {
  id: string;
  text: string;
  type: 'drag_sort';
  items: string[];
}

export interface KnowledgeMapQuestion {
  id: string;
  text: string;
  type: 'knowledge_map';
  tree: KnowledgeNode[];
}

export interface KnowledgeNode {
  id: string;
  label: string;
  children?: KnowledgeNode[];
}

export type QuestionAnswer =
  | { type: 'radio'; value: string; other_text?: string; question_id?: string }
  | { type: 'checkbox'; values: string[]; question_id?: string }
  | { type: 'slider'; value: number; question_id?: string }
  | { type: 'drag_sort'; order: string[]; question_id?: string }
  | { type: 'knowledge_map'; checked: string[]; question_id?: string };

export interface QuestionAnswerRecord {
  question: AgentQuestion;
  answers: QuestionAnswer[];
  skipped?: boolean;
  summary: string;
  details: { question: string; answer: string }[];
}

// ========================================
// SSE（前端流式事件，非 OpenAPI schema）
// ========================================

export type SSEEventType =
  | 'text_delta'
  | 'thinking'
  | 'tool_call'
  | 'tool_result'
  | 'question'
  | 'agent_switch'
  | 'subagent_start'
  | 'subagent_thinking'
  | 'subagent_text'
  | 'subagent_done'
  | 'select_repos'
  | 'session_projects'
  | 'done'
  | 'error';

export interface SSEEvent {
  event: SSEEventType;
  data: Record<string, unknown>;
}

export interface SSETextDelta {
  content: string;
}

export interface SSEThinking {
  content: string;
}

export interface SSEToolCall {
  call_id: string;
  name: string;
  args: Record<string, unknown>;
}

export interface SSEToolResult {
  call_id: string;
  result: unknown;
  duration_ms?: number;
}

export interface SSEAgentSwitch {
  from: AgentId;
  to: AgentId;
  reason: string;
}

export interface SSESubagentStart {
  agent_id: AgentId;
  task?: string;
  reason?: string;
}

export interface SSESubagentThinking {
  agent_id: AgentId;
  content: string;
}

export interface SSESubagentText {
  agent_id: AgentId;
  content: string;
}

export interface SSESubagentDone {
  agent_id: AgentId;
  status?: string;
  thinking?: string;
  output?: string;
}

export interface SSEDone {
  usage: { tokens: number; input_tokens?: number; output_tokens?: number };
  iterations: number;
}

export interface SSEError {
  code: string;
  message: string;
}

// ========================================
// Settings / Profile 前端收紧（与 SettingsOut 兼容的常用别名）
// ========================================

export type LlmApiFormat = 'openai' | 'anthropic' | 'google' | 'ollama' | 'custom';

export type AgentSpeakingStyle =
  | 'default'
  | 'warm'
  | 'sharp'
  | 'professional'
  | 'humorous'
  | 'concise'
  | 'mentor'
  | 'socratic';

export type ProficiencyLevel = 'none' | 'basic' | 'intermediate' | 'advanced' | 'mastered';
export type ProficiencySource = 'self_reported' | 'inferred' | 'assessed';

export interface TechProficiencyEntry {
  level: ProficiencyLevel;
  source: ProficiencySource;
  confidence: number;
  evidence: string[];
  updated_at: string;
}

export type LearningStyle = 'hands_on' | 'theoretical' | 'visual';
export type Verbosity = 'concise' | 'balanced' | 'detailed';

export interface LearningPreferences {
  style: LearningStyle;
  depth_first: boolean;
  verbosity: Verbosity;
  language: string;
}

export type GoalStatus = 'active' | 'completed' | 'paused';

/** 导入助手上下文（前端组装，非独立 schema） */
export interface ImportAssistRepoSummary {
  key: string;
  language?: string | null;
  stars?: number;
  already_imported?: boolean;
  description?: string | null;
}

export interface ImportAssistImportedProject {
  name: string;
  language?: string | null;
  progress?: string;
  stars?: number;
  description?: string | null;
}

export interface ImportAssistContext {
  mode: 'stars' | 'urls' | 'search';
  available_repo_keys?: string[];
  selected_repo_keys?: string[];
  available_repos?: ImportAssistRepoSummary[];
  imported_projects?: ImportAssistImportedProject[];
}

export interface SelectReposEvent {
  repo_keys: string[];
  action: 'set' | 'add' | 'remove';
  reason?: string;
  count?: number;
}
