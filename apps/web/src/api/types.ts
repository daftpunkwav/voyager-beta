/** Voyager 领域类型兼容入口(沿用旧 IApiClient 形态,内部按 capability 域归类)。
 *
 * 旧 page / hook / component 大量 import 自 'types' 包与本文件的前端专属类型。
 * 后端 capability 返回结构略有不同(Repo → repo / project_id → source_id 等),
 * 实际页面中以**结构化使用**为主,字段名差异由 legacyApi 在边界处归一化。
 *
 * 本文件仅声明迁移后页面**实际访问**的字段子集;全量定义参考 docs/audit/04-frontend-migration-detail.html §3。
 *
 * 注意:本层仅为兼容入口,新代码禁止引用本文件,
 * 应直接用 @/bridge/client 的 callCapability + 各自的领域类型。
 */

export type { ApiResponse, SSEEvent } from '@/bridge/legacyApi';
import type { ApiResponse as _ApiResponse } from '@/bridge/legacyApi';

// ---------- 用户 / GitHub ----------

export interface User {
  id: string;
  name: string;
  username?: string;
  email?: string;
  avatar_url?: string;
  github_login?: string;
  github_bound?: boolean;
  github_token_masked?: string;
  /** 兼容旧字段 */
  pat_masked?: string;
  /** 扩展:角色 */
  role?: 'owner' | 'user' | 'guest';
}

export interface GitHubAccount {
  id: string;
  username: string;
  pat_masked: string;
}

export interface StarsListResult {
  items: Array<{
    full_name: string;
    description: string;
    stars: number;
    language: string | null;
    html_url: string;
  }>;
  total: number;
}

export interface StarRepo {
  id?: string;
  full_name: string;
  owner: string;
  repo: string;
  description: string;
  stars: number;
  language: string | null;
  html_url: string;
  url?: string;
  avatar_url?: string;
  topics?: string[];
  fetched_at?: number;
  already_imported?: boolean;
}

export interface SelectReposEvent {
  intro: string;
  repos: StarRepo[];
}

// ---------- Project (旧) → Repo (新) ----------

export interface Project {
  id: string;
  name: string;
  full_name: string;
  description: string;
  language: string | null;
  stars: number;
  category_id: string | null;
  category_ids?: string[];
  tag_ids?: string[];
  tags?: Array<string | Tag>;
  progress: 'none' | 'learning' | 'learned' | 'mastered';
  source: 'github' | 'gitee' | 'manual' | 'imported';
  status: 'importing' | 'ready' | 'failed';
  local_path?: string;
  readme?: string;
  category?: Category | null;
  notes_count?: number;
  added_ts: number;
  updated_ts: number;
  imported_at?: string;
  relevance?: number;
  /** 兼容旧字段 */
  project_id?: string;
  url?: string;
  html_url?: string;
  created_at?: number;
  updated_at?: number;
  cached?: boolean;
}

export interface ProjectListParams {
  search?: string;
  category_id?: string;
  language?: string;
  progress?: Project['progress'];
  tag_id?: string;
  sort_by?: 'name' | 'stars' | 'imported_at' | 'updated_at';
  sort_order?: 'asc' | 'desc';
  page?: number;
  page_size?: number;
}

export interface PaginatedList<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ProjectReadme {
  content: string;
  html_url?: string;
}

export interface ProjectStats {
  by_progress: Record<string, number>;
  by_category: Record<string, number>;
  by_language: Record<string, number>;
  total: number;
  cached?: number;
  fetched_at?: number;
}

export interface ProjectIndexProgress {
  project_id: string;
  status: 'idle' | 'indexing' | 'ready' | 'failed';
  files_indexed: number;
  total_files: number;
  updated_ts: number;
  error?: string;
}

export interface CreateProjectInput {
  url: string;
  name?: string;
  category_id?: string;
  progress?: Project['progress'];
  note?: string;
  /** 旧字段(项目 → 资源源过渡期保留) */
  full_name?: string;
  description?: string;
  language?: string | null;
  stars?: number;
}

export interface UpdateProjectInput {
  progress?: Project['progress'];
  category_id?: string | null;
  tag_ids?: string[];
  local_path?: string;
  readme?: string;
}

// ---------- Category / Tag ----------

export interface Category {
  id: string;
  name: string;
  count?: number;
  icon?: string;
  is_preset?: boolean;
  preset_id?: string;
  color?: string;
  sort_order?: number;
}

export type Tag = string | { id: string; name: string; count?: number };

export interface TagRef {
  id: string;
  name: string;
  count?: number;
}

export interface SetProjectTagsResult {
  project_id: string;
  tag_ids: string[];
}

// ---------- Note ----------

export interface Note {
  id: string;
  title: string;
  content: string;
  excerpt?: string;
  source_id: string;
  project_id?: string;
  node_id?: string;
  tags: string[];
  created_ts: number;
  updated_ts: number;
  created_at?: number;
  updated_at?: number;
}

export interface NoteCreate {
  title: string;
  content: string;
  source_id?: string;
  project_id?: string;
  tags?: string[];
}

export type NoteUpdate = Partial<NoteCreate>;

// ---------- Graph ----------

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphNode {
  id: string;
  name: string;
  full_name?: string;
  language?: string | null;
  stars: number;
  category_id?: string | null;
  progress?: Project['progress'];
  foundation_score?: number;
  hubness?: number;
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

export interface GraphStats {
  node_count: number;
  edge_count: number;
  cluster_count: number;
  updated_ts: number;
}

export interface GraphGuideSession {
  session_id: string;
  messages: AgentMessage[];
}

export interface CodeGraphNode {
  id: string;
  type: 'file' | 'function' | 'class' | 'module';
  name: string;
  path: string;
  language: string;
  size: number;
  complexity?: number;
}

export interface CodeGraphEdge {
  source: string;
  target: string;
  relation: 'imports' | 'calls' | 'extends' | 'implements';
}

export interface CodeGraphData {
  nodes: CodeGraphNode[];
  edges: CodeGraphEdge[];
  stats: { node_count: number; edge_count: number };
}

export interface ImportResult {
  queued: string[];
  failed: Array<{ url: string; reason: string }>;
}

export interface IndexStatus {
  status: 'idle' | 'running' | 'paused' | 'failed' | 'done';
  total: number;
  indexed: number;
  failed: number;
  updated_ts: number;
}

// ---------- Settings ----------

export interface Settings {
  appearance: { theme: 'dark' | 'light' | 'system'; font_scale: number; code_font: string };
  llm: {
    default_provider: string;
    default_model: string;
    temperature: number;
    max_output_tokens: number;
  };
  agent: {
    rounds_max: number;
    rounds_tool_max: number;
    arbiter_mode: 'queue' | 'auto' | 'guide';
    direct_chat: boolean;
    proactive_per_session: number;
    proactive_per_day: number;
    proactive_quiet_start: number;
    proactive_quiet_end: number;
    workspace_dir: string;
    network_mode: 'off' | 'whitelist' | 'all';
    network_domains: string[];
    subagents_max_concurrent: number;
    memory_retention_days: number;
    style: string;
  };
  privacy: { activity_report: boolean };
  /** 兼容旧字段 — flat 命名 */
  llm_configured?: boolean;
  llm_model?: string;
  llm_default_provider_id?: string;
  llm_providers?: LlmProviderConfig[];
  llm_default_model?: string;
  llm_api_base?: string;
  llm_api_format?: 'openai' | 'anthropic' | 'google' | 'ollama' | 'custom';
  llm_api_key_masked?: string;
  llm_available_models?: string[];
  llm_provider?: string;
  llm_provider_display_name?: string;
  agent_code_of_conduct?: string;
  agent_guidelines?: Array<{ id: string; text: string; enabled: boolean }>;
  agent_llm_configs?: Record<string, AgentLlmConfig>;
  agent_speaking_styles?: Record<string, AgentSpeakingStyle>;
}

export type SettingsUpdate = Partial<Settings>;

// ---------- LLM ----------

export type LlmApiFormat = 'openai' | 'anthropic' | 'google' | 'ollama' | 'custom';

export interface LlmProviderConfig {
  id: string;
  preset_id: string;
  label: string;
  display_name?: string;
  base_url?: string;
  api_base?: string;
  has_api_key: boolean;
  configured?: boolean;
  api_key_masked?: string;
  api_format: LlmApiFormat;
  models: string[];
  available_models?: string[];
  enabled: boolean;
  default_model?: string;
  temperature?: number;
  max_output_tokens?: number;
}

export interface AgentLlmConfig {
  agent_id: string;
  provider_id: string;
  model: string;
  temperature?: number;
  max_output_tokens?: number;
}

export interface AgentSpeakingStyle {
  agent_id: string;
  tone: 'concise' | 'normal' | 'warm' | 'formal';
  language: string;
  catchphrases?: string[];
}

export interface LlmUsageSummary {
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost: number;
  totals?: {
    input: number;
    output: number;
    cost: number;
    calls: number;
  };
  by_model: Record<string, { input: number; output: number; cost: number; calls: number }>;
  by_provider?: Record<string, { input: number; output: number; cost: number; calls: number }>;
  by_day: Array<{ date: string; input: number; output: number; cost: number; calls: number }>;
  heatmap?: Array<{ date: string; hour: number; tokens: number; cost: number }>;
}

// ---------- Activity / Trending ----------

export interface ActivityItem {
  id: string;
  actor: 'user' | 'agent' | 'system';
  type: string;
  payload: Record<string, unknown>;
  ts: number;
  trace_id?: string;
  project_id?: string;
  source_id?: string;
  session_id?: string;
  agent_id?: AgentId;
  title?: string;
  href?: string;
}

export interface TrendingRepo {
  full_name: string;
  owner: string;
  repo: string;
  description: string;
  stars: number;
  language: string | null;
  html_url: string;
  avatar_url?: string;
}

export type TrendingPeriod = 'daily' | 'weekly' | 'monthly';

export interface RecommendedProject {
  project: Project;
  reason: string;
  score: number;
}

export interface OverviewRecentNote {
  id: string;
  title: string;
  excerpt: string;
  updated_ts: number;
}

// ---------- Agent / Memory ----------

export type AgentId =
  | 'hub'
  | 'scout'
  | 'mentor'
  | 'navigator'
  | 'curator'
  | 'scribe'
  | 'atlas'
  | 'lucien'
  | 'iris'
  | 'elio'
  | 'miyai';

export interface AgentSession {
  id: string;
  title: string;
  project_id?: string | null;
  project_ids?: string[];
  agent: AgentId;
  created_ts: number;
  updated_ts: number;
  source?: 'chat' | 'analyze' | 'import' | 'graph';
  status?: 'active' | 'archived';
}

export interface AgentSessionDetail extends AgentSession {
  messages: AgentMessage[];
}

export interface AgentProfile {
  id: string;
  key: AgentId;
  name?: string;
  display_name: string;
  style: string;
  system_prompt: string;
  default_mode: string;
  tool_allow: string[] | null;
  description?: string;
  avatar?: string;
  catchphrases?: string[];
}

export interface AgentMessage {
  id: string;
  session_id: string;
  agent: AgentId;
  role: 'user' | 'assistant' | 'tool' | 'system';
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
  agent_switch?: { from: string; to: string; reason?: string };
  created_at: string;
  created_ts?: number;
}

export interface ToolCallData {
  name: string;
  args: Record<string, unknown>;
  result?: unknown;
  ts?: number;
  status?: 'running' | 'ok' | 'error';
}

export type QuestionItem =
  | RadioQuestion
  | CheckboxQuestion
  | SliderQuestion
  | DragSortQuestion
  | KnowledgeMapQuestion;

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

export interface AgentPermissions {
  global: { can_write: boolean; can_delete: boolean; can_publish: boolean };
  per_capability: Record<string, { can_call: boolean }>;
}

export interface MemoryItem {
  id: string;
  content: string;
  category: 'preference' | 'fact' | 'context' | 'goal' | 'skill';
  created_ts: number;
  source: 'user' | 'inferred' | 'agent';
  confidence?: number;
}

export interface MemoryProposal {
  id: string;
  content: string;
  category: MemoryItem['category'];
  reason: string;
  status: 'pending' | 'accepted' | 'rejected';
  created_ts: number;
}

export interface UserProfile {
  identity: LearnerIdentity;
  goals: Goal[];
  tech_proficiency: TechProficiencyEntry[];
  learning_style: string;
  verbosity: 'concise' | 'normal' | 'detailed';
  preferences: LearningPreferences;
  memory_items?: MemoryItem[];
  pending_memory_proposals?: MemoryProposal[];
}

export interface LearnerIdentity {
  background: string;
  current_role: string;
  experience_years: number;
  languages: string[];
}

export interface Goal {
  id: string;
  title?: string;
  text?: string;
  status: 'active' | 'completed' | 'paused';
  progress: number;
}

export interface TechProficiencyEntry {
  tech: string;
  level: 'novice' | 'intermediate' | 'advanced' | 'expert';
  source: 'self' | 'inferred' | 'verified';
}

export interface LearningPreferences {
  preferred_formats: string[];
  avoid_topics: string[];
  pace: 'slow' | 'normal' | 'fast';
}

export interface ContextWindowSegment {
  label: string;
  tokens: number;
  type?: 'system' | 'history' | 'tools' | 'memory' | 'output';
}

export interface ContextWindowStats {
  total: number;
  total_tokens: number;
  context_limit: number;
  max: number;
  segments: ContextWindowSegment[];
  model: string;
  input_tokens: number;
  output_tokens: number;
}

export interface ImportAssistContext {
  intent: string;
  candidate_repos: StarRepo[];
  hints?: string[];
}

// ---------- SSE 事件(旧 v1 形态) ----------

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

export interface SSETextDelta {
  type: 'text_delta';
  text: string;
}

export interface SSEThinking {
  type: 'thinking';
  text: string;
}

export interface SSEToolCall {
  type: 'tool_call';
  name: string;
  args: Record<string, unknown>;
  call_id: string;
}

export interface SSEToolResult {
  type: 'tool_result';
  call_id: string;
  result: unknown;
  status: 'ok' | 'error';
}

export interface SSEAgentSwitch {
  type: 'agent_switch';
  from: string;
  to: string;
  reason?: string;
}

export interface SSESubagentStart {
  type: 'subagent_start';
  agentId: AgentId;
  task?: string;
}

export interface SSESubagentDone {
  type: 'subagent_done';
  agentId: AgentId;
  status: 'ok' | 'error';
  output?: string;
}

export interface SSEError {
  type: 'error';
  message: string;
  code?: string;
}

// ---------- 错误形态 ----------

export interface ApiError {
  code: string;
  message: string;
  status?: number;
  details?: Record<string, unknown>;
}

// ---------- 兼容层对外类型 ----------
// 完整 84 方法由 bridge/legacyApi.ts 的 LegacyApiClient 实现,
// 此处声明为结构兼容,具体方法签名以 LegacyApiClient 为准。
// 兼容层:放宽 any(见文件顶部注释;旧 store 直接 .data 访问,需 any 推断)
export type IApiClient = {
  [k: string]: (...args: any[]) => Promise<_ApiResponse<any>> | AsyncGenerator<any> | any;
};

// ---------- 兼容层(legacyApi 对外类型) ----------
// IApiClient 由 bridge/legacyApi.ts 内部声明并 export,这里不再重复(避免签名漂移)。

// SSE 形态在新前端被弃用,旧 hook 仍可能消费 — 由桥接层转译
