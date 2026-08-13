import type {
  ActivityItem,
  AgentId,
  AgentMessage,
  AgentPermissions,
  AgentProfile,
  AgentSession,
  ApiResponse,
  Category,
  ContextWindowStats,
  CreateProjectInput,
  GitHubAccount,
  GraphData,
  ImportAssistContext,
  ImportResult,
  Note,
  OverviewRecentNote,
  PaginatedList,
  Project,
  ProjectListParams,
  ProjectReadme,
  ProjectStats,
  QuestionAnswer,
  RecommendedProject,
  Settings,
  SSEEvent,
  StarRepo,
  StarsListResult,
  Tag,
  TrendingPeriod,
  TrendingRepo,
  TrendingScoutIntroParams,
  User,
  UserProfile,
  LlmUsageSummary,
} from './types';
// 契约类型权威源：types（经 ./types 再导出）
export type { paths, components, User as ContractUser } from 'types';

/**
 * IApiClient — 后端 API 客户端统一接口契约
 */
export interface IApiClient {
  me(): Promise<ApiResponse<User>>;

  listGithubAccounts(): Promise<ApiResponse<GitHubAccount[]>>;
  bindGithub(params: { username: string; pat: string }): Promise<ApiResponse<GitHubAccount>>;
  unbindGithub(id: string): Promise<ApiResponse<{ success: boolean }>>;
  listStars(params?: {
    username?: string;
    refresh?: boolean;
  }): Promise<ApiResponse<StarsListResult>>;
  importProjects(
    repos: Array<{ owner: string; repo: string; url: string }>
  ): Promise<ApiResponse<ImportResult>>;

  listProjects(params?: ProjectListParams): Promise<ApiResponse<PaginatedList<Project>>>;
  getProject(id: string): Promise<ApiResponse<Project>>;
  getProjectReadme(id: string): Promise<ApiResponse<ProjectReadme>>;
  createProject(data: CreateProjectInput): Promise<ApiResponse<Project>>;
  updateProject(id: string, data: Partial<Project>): Promise<ApiResponse<Project>>;
  deleteProject(id: string): Promise<ApiResponse<{ success: boolean }>>;
  updateProgress(
    id: string,
    progress: Project['progress']
  ): Promise<ApiResponse<{ id: string; progress: string }>>;
  getProjectStats(): Promise<ApiResponse<ProjectStats>>;
  exportProjects(): Promise<ApiResponse<Project[]>>;

  listCategories(): Promise<ApiResponse<Category[]>>;
  createCategory(data: { name: string }): Promise<ApiResponse<Category>>;
  updateCategory(id: string, data: { name: string }): Promise<ApiResponse<Category>>;
  deleteCategory(id: string): Promise<ApiResponse<{ success: boolean }>>;
  listTags(): Promise<ApiResponse<Tag[]>>;
  createTag(data: { name: string }): Promise<ApiResponse<Tag>>;
  deleteTag(id: string): Promise<ApiResponse<{ success: boolean }>>;
  setProjectTags(
    projectId: string,
    tagIds: string[]
  ): Promise<ApiResponse<{ project_id: string; tag_ids: string[] }>>;

  listNotes(projectId: string): Promise<ApiResponse<Note[]>>;
  listAllNotes(): Promise<ApiResponse<Note[]>>;
  getNote(id: string): Promise<ApiResponse<Note>>;
  createNote(
    projectId: string,
    data: { title: string; content: string }
  ): Promise<ApiResponse<Note>>;
  updateNote(id: string, data: Partial<Note>): Promise<ApiResponse<Note>>;
  deleteNote(id: string): Promise<ApiResponse<{ success: boolean }>>;

  getGraph(params?: {
    min_similarity?: number;
    max_edges?: number;
  }): Promise<ApiResponse<GraphData>>;

  getCrossEdges(): Promise<
    ApiResponse<{ edges: Array<Record<string, unknown>>; stats: { edge_count: number } }>
  >;
  getRecommendEdges(): Promise<
    ApiResponse<{
      edges: Array<Record<string, unknown>>;
      stats: { edge_count: number };
      meta?: Record<string, unknown>;
    }>
  >;
  listCodeGraphIndexStatuses(): Promise<
    ApiResponse<{
      items: Array<Record<string, unknown>>;
      active: Array<Record<string, unknown>>;
      stats: { total: number; running: number; ready: number; failed: number };
    }>
  >;
  cancelCodeGraphIndex(
    projectId: string,
  ): Promise<ApiResponse<import('@/components/code-graph/types').GraphIndexStatus>>;
  getCodeGraphStatus(projectId: string): Promise<ApiResponse<import('@/components/code-graph/types').GraphIndexStatus>>;
  triggerCodeGraphIndex(
    projectId: string,
    body?: { mode?: 'fast' | 'moderate' | 'full' },
  ): Promise<ApiResponse<import('@/components/code-graph/types').GraphIndexStatus>>;
  refreshCodeGraphIndex(
    projectId: string,
    body?: { mode?: 'fast' | 'moderate' | 'full' },
  ): Promise<ApiResponse<import('@/components/code-graph/types').GraphIndexStatus>>;
  deleteCodeGraphIndex(
    projectId: string,
  ): Promise<ApiResponse<import('@/components/code-graph/types').GraphIndexStatus>>;
  getCodeGraph(
    projectId: string,
    params?: { max_nodes?: number },
  ): Promise<ApiResponse<Record<string, unknown>>>;
  getCodeArchitecture(projectId: string): Promise<ApiResponse<Record<string, unknown>>>;
  traceCodeGraph(
    projectId: string,
    body: { symbol: string; direction?: string; depth?: number },
  ): Promise<ApiResponse<Record<string, unknown>>>;
  searchCodeGraph(
    projectId: string,
    body: { query: string; label?: string; limit?: number },
  ): Promise<ApiResponse<Record<string, unknown>>>;
  batchIndexCodeGraph(
    projectIds: string[],
    mode?: 'fast' | 'moderate' | 'full',
  ): Promise<ApiResponse<{ queued: string[]; failed: string[] }>>;

  getLlmUsage(days?: number): Promise<ApiResponse<LlmUsageSummary>>;

  getSettings(): Promise<ApiResponse<Settings>>;
  updateSettings(data: Partial<Settings>): Promise<ApiResponse<Settings>>;
  saveLlmApiKey(
    apiKey: string,
    providerId?: string,
  ): Promise<ApiResponse<{ masked: string; provider_id?: string | null }>>;
  testLLM(params?: {
    model?: string;
    provider_id?: string;
  }): Promise<
    ApiResponse<{
      success: boolean;
      latency_ms: number;
      model: string;
      reply?: string;
      error?: string;
      litellm_model?: string;
      provider_id?: string | null;
    }>
  >;

  listTrending(params?: {
    period?: TrendingPeriod;
    language?: string;
  }): Promise<ApiResponse<TrendingRepo[]>>;
  /** Scout 总览 trending 悬停介绍（SSE · 未来对接 LLM） */
  streamTrendingScoutIntro(
    params: TrendingScoutIntroParams,
    signal?: AbortSignal
  ): AsyncGenerator<SSEEvent>;
  listActivities(): Promise<ApiResponse<ActivityItem[]>>;
  listRecommendedProjects(params?: {
    limit?: number;
  }): Promise<ApiResponse<RecommendedProject[]>>;
  listOverviewRecentNotes(params?: {
    limit?: number;
  }): Promise<ApiResponse<OverviewRecentNote[]>>;

  listAgentSessions(): Promise<ApiResponse<AgentSession[]>>;
  getAgentSession(
    id: string
  ): Promise<ApiResponse<AgentSession & { messages: AgentMessage[] }>>;
  createAgentSession(): Promise<ApiResponse<AgentSession>>;
  deleteAgentSession(id: string): Promise<ApiResponse<{ success: boolean }>>;
  updateAgentSession(
    id: string,
    data: {
      title?: string;
      project_id?: string | null;
      project_ids?: string[];
    }
  ): Promise<ApiResponse<AgentSession>>;
  getAgentProfiles(): Promise<ApiResponse<AgentProfile[]>>;
  getUserProfile(): Promise<ApiResponse<UserProfile>>;
  updateUserProfile(data: Partial<UserProfile>): Promise<ApiResponse<UserProfile>>;
  /** 清除 Agent 关于用户的画像记忆（不删除对话） */
  clearUserMemory(): Promise<ApiResponse<UserProfile>>;
  /** 确认待处理记忆提案 */
  acceptMemoryProposal(proposalId: string): Promise<ApiResponse<UserProfile>>;
  /** 拒绝待处理记忆提案 */
  rejectMemoryProposal(proposalId: string): Promise<ApiResponse<UserProfile>>;
  getPermissions(): Promise<ApiResponse<AgentPermissions>>;

  chatAgent(sessionId: string, message: string, signal?: AbortSignal): AsyncGenerator<SSEEvent>;
  answerQuestion(
    sessionId: string,
    questionId: string,
    answers: QuestionAnswer[],
    signal?: AbortSignal,
    skipped?: boolean
  ): AsyncGenerator<SSEEvent>;
  analyzeProject(projectId: string, agent?: AgentId, signal?: AbortSignal): AsyncGenerator<SSEEvent>;
  /** Scribe 生成笔记大纲/草稿（SSE） */
  generateNote(
    projectId: string,
    params?: { mode?: 'project' | 'standalone'; topic?: string },
    signal?: AbortSignal
  ): AsyncGenerator<SSEEvent>;

  /** 当前会话的上下文窗口用量 */
  getContextWindow(sessionId?: string | null): Promise<ApiResponse<ContextWindowStats>>;

  /** GitHub 仓库搜索（导入弹窗） */
  searchGithubRepos(query: string): Promise<ApiResponse<StarRepo[]>>;

  /** 导入助手对话（SSE） */
  importAssistChat(
    message: string,
    context: ImportAssistContext,
    signal?: AbortSignal
  ): AsyncGenerator<SSEEvent>;

  /** 图谱向导对话（SSE，专用 Atlas Agent） */
  graphGuideChat(
    message: string,
    context?: { selected_node_id?: string | null },
    signal?: AbortSignal
  ): AsyncGenerator<SSEEvent>;

}

async function createApiClient(): Promise<IApiClient> {
  const { RealApiClient } = await import('./real');
  return new RealApiClient();
}

let apiClientPromise: Promise<IApiClient> | null = null;
let apiClient: IApiClient | null = null;

export function getApiClient(): Promise<IApiClient> {
  if (!apiClientPromise) {
    apiClientPromise = createApiClient();
  }
  return apiClientPromise;
}

export async function initApiClient(): Promise<IApiClient> {
  apiClient = await getApiClient();
  return apiClient;
}

export function getApi(): IApiClient {
  if (!apiClient) {
    throw new Error('ApiClient not initialized. Call initApiClient() in main.tsx first.');
  }
  return apiClient;
}
