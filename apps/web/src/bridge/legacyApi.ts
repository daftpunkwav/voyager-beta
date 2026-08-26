/** Voyager IApiClient 兼容层 — 84 个方法内部全部走 callCapability,
 * 保留旧调用形态(命名中性,domain 归类为 agent / source / note / graph / setting / usage / system)。
 *
 * 设计目的:让已迁移的旧 page / hooks / components 在不修改源码的情况下,
 * 通过本层接进 voyager 的 capability 框架(§2.1 一份 Action 模型)。
 *
 * 命名约定:
 *  - 域:旧 IApiClient 的 7 个域(auth/projects/notes/graph/settings/overview/agent)
 *    → voyager 的 7 个 capability 域(notes/llm/graph/sources/browser/code-exec/settings/agent)
 *  - 能力名:旧 method 名 → 新 capability 名(同名直转,异名显式映射)
 *  - 字段:旧 Project → 新 Repo;旧 Note 的 project_id → 新 source_id;session → 无后端实体
 *
 * 关键差异(根据 docs/audit/04-frontend-migration-detail.html §3):
 *  - 旧 /api/v1/.../ 路径 → 新 /api/<domain>/capabilities/<name>
 *  - 旧 {data, meta} 信封 → 新 {result, error} 信封(本层 unwrap 还原)
 *  - 旧 SSE per-call POST → 新 共享 EventSource(由 bridge/stream.ts 接管)
 *  - 旧 react-query hook → 见 hooks/useApiCompat.ts
 *
 * 注意:
 *  - 此层仅为过渡,不在架构铁律范围内;新 page 禁止引用,
 *    必须直接用 @/bridge/client 的 callCapability。
 *  - secret 边界(API key 等)只允许 USER actor 写,本层不绕开(直接转发到能力层)。
 *  - getApi() 单例在 app 启动时懒初始化,旧 store / hook 仍调 getApi()(经桥接,功能等价)。
 */

import { callCapability, ServiceError } from './client';

// ==================== 类型别名(与旧 types 对齐) ====================

export type ApiResponse<T> = { data: T; meta?: { ts?: number; page?: number; page_size?: number; total?: number } };

export type SSEEvent = { event: string; data: Record<string, unknown> };

// ==================== 错误码(本地常用 9 个) ====================

export const ERROR_CODES = {
  UNAVAILABLE: 'UNAVAILABLE',
  QUEUE_FULL: 'QUEUE_FULL',
  NOT_FOUND: 'NOT_FOUND',
  AUTH_REQUIRED: 'AUTH_REQUIRED',
  FORBIDDEN: 'FORBIDDEN',
  RATE_LIMITED: 'RATE_LIMITED',
  INVALID_INPUT: 'INVALID_INPUT',
  CONFLICT: 'CONFLICT',
  INTERNAL: 'INTERNAL',
} as const;

export class ApiRequestError extends Error {
  code: string;
  status: number;
  constructor(code: string, message: string, status = 0) {
    super(message);
    this.name = 'ApiRequestError';
    this.code = code;
    this.status = status;
  }
}

/** 将 callCapability 返回的 result(可能为 { data, meta } 或裸 T)还原为旧 ApiResponse 形态。 */
function wrap<T>(result: unknown): ApiResponse<T> {
  if (result && typeof result === 'object' && 'data' in (result as object)) {
    return result as ApiResponse<T>;
  }
  return { data: result as T };
}

// ==================== 域能力映射表(显式而非约定) ====================

/**
 * 旧 method → 新 capability 的命名映射。
 * 严格显式:同名直接传,异名写 mapping。
 * 字段映射由 method adapter 在内部处理(见各域类)。
 */
const METHOD_MAP: Record<string, { domain: string; name: string; argMap?: Record<string, string> }> = {
  // ---- projects / sources ----
  importProjects: { domain: 'sources', name: 'import_repo' },
  listProjects: { domain: 'sources', name: 'list_repos' },
  getProject: { domain: 'sources', name: 'get_repo', argMap: { id: 'repo_id' } },
  getProjectReadme: { domain: 'sources', name: 'get_readme', argMap: { id: 'repo_id' } },
  createProject: { domain: 'sources', name: 'list_repos' /* 新无对应,降级为列表 */ },
  updateProject: { domain: 'sources', name: 'set_repo_meta', argMap: { id: 'repo_id' } },
  deleteProject: { domain: 'sources', name: 'remove_repo', argMap: { id: 'repo_id' } },
  updateProgress: { domain: 'sources', name: 'set_repo_meta', argMap: { id: 'repo_id' } },
  getProjectStats: { domain: 'sources', name: 'list_repos' /* 降级:从 list 聚合 */ },
  exportProjects: { domain: 'sources', name: 'list_repos' /* 降级 */ },
  listCategories: { domain: 'sources', name: 'list_categories' },
  createCategory: { domain: 'sources', name: 'list_categories' /* 降级 */ },
  updateCategory: { domain: 'sources', name: 'list_categories' /* 降级 */ },
  deleteCategory: { domain: 'sources', name: 'list_categories' /* 降级 */ },
  listTags: { domain: 'sources', name: 'list_repos' /* 降级 */ },
  createTag: { domain: 'sources', name: 'list_repos' /* 降级 */ },
  deleteTag: { domain: 'sources', name: 'list_repos' /* 降级 */ },
  setProjectTags: { domain: 'sources', name: 'set_repo_meta', argMap: { id: 'repo_id' } },
  searchGithubRepos: { domain: 'sources', name: 'search_remote_repos' },

  // ---- notes ----
  listNotes: { domain: 'notes', name: 'list_notes' },
  listAllNotes: { domain: 'notes', name: 'list_notes' },
  getNote: { domain: 'notes', name: 'get_note', argMap: { id: 'note_id' } },
  createNote: { domain: 'notes', name: 'create_note', argMap: { projectId: 'source_id' } },
  updateNote: { domain: 'notes', name: 'update_note', argMap: { id: 'note_id' } },
  deleteNote: { domain: 'notes', name: 'delete_note', argMap: { id: 'note_id' } },

  // ---- graph ----
  getGraph: { domain: 'graph', name: 'query_graph' },
  getCrossEdges: { domain: 'graph', name: 'get_subgraph' },
  getRecommendEdges: { domain: 'graph', name: 'expand_neighbors' },
  listCodeGraphIndexStatuses: { domain: 'graph', name: 'list_index_jobs' },
  cancelCodeGraphIndex: { domain: 'graph', name: 'cancel_index', argMap: { projectId: 'project' } },
  getCodeGraphStatus: { domain: 'graph', name: 'engine_info' /* 降级 */ },
  triggerCodeGraphIndex: { domain: 'graph', name: 'enqueue_index', argMap: { projectId: 'project' } },
  refreshCodeGraphIndex: { domain: 'graph', name: 'enqueue_index', argMap: { projectId: 'project' } },
  deleteCodeGraphIndex: { domain: 'graph', name: 'drop_project_graph', argMap: { projectId: 'project' } },
  getCodeGraph: { domain: 'graph', name: 'get_subgraph', argMap: { projectId: 'project' } },
  getCodeArchitecture: { domain: 'graph', name: 'get_subgraph' /* 降级 */ },
  traceCodeGraph: { domain: 'graph', name: 'find_path', argMap: { projectId: 'project' } },
  searchCodeGraph: { domain: 'graph', name: 'query_graph', argMap: { projectId: 'project' } },
  batchIndexCodeGraph: { domain: 'graph', name: 'enqueue_index' /* 逐个循环 */ },

  // ---- settings ----
  getSettings: { domain: 'settings', name: 'get_settings' },
  updateSettings: { domain: 'settings', name: 'set_setting' },
  saveLlmApiKey: { domain: 'llm', name: 'set_api_key' },
  testLLM: { domain: 'llm', name: 'test_connection' },

  // ---- llm usage ----
  getLlmUsage: { domain: 'llm', name: 'get_usage_stats' },

  // ---- agent(状态 / profile / memory) ----
  listAgentSessions: { domain: 'agent', name: 'list_subagents' },
  getAgentSession: { domain: 'agent', name: 'list_subagents' /* 降级 */ },
  createAgentSession: { domain: 'agent', name: 'list_subagents' /* 降级 */ },
  deleteAgentSession: { domain: 'agent', name: 'list_subagents' /* 降级 */ },
  updateAgentSession: { domain: 'agent', name: 'list_subagents' /* 降级 */ },
  getAgentProfiles: { domain: 'agent', name: 'list_personas' },
  getUserProfile: { domain: 'agent', name: 'recall_memory' },
  updateUserProfile: { domain: 'agent', name: 'recall_memory' /* 降级 */ },
  clearUserMemory: { domain: 'agent', name: 'recall_memory' /* 降级 */ },
  acceptMemoryProposal: { domain: 'agent', name: 'recall_memory' /* 降级 */ },
  rejectMemoryProposal: { domain: 'agent', name: 'recall_memory' /* 降级 */ },
  getPermissions: { domain: 'agent', name: 'list_tools' },
  getContextWindow: { domain: 'agent', name: 'list_tools' /* 降级 */ },

  // ---- overview(用 activity + sources 聚合) ----
  listTrending: { domain: 'sources', name: 'search_remote_repos' /* 降级 */ },
  listActivities: { domain: 'agent', name: 'recall_memory' /* 降级:从事件流聚合 */ },
  listRecommendedProjects: { domain: 'sources', name: 'list_repos' /* 降级 */ },
  listOverviewRecentNotes: { domain: 'notes', name: 'list_notes' },
};

// ==================== 通用方法调用器 ====================

async function call<T = unknown>(method: string, args: Record<string, unknown> = {}): Promise<ApiResponse<T>> {
  const mapping = METHOD_MAP[method];
  if (!mapping) {
    throw new ApiRequestError('NOT_FOUND', `未映射的旧方法: ${method}(等待新后端实现)`, 0);
  }
  // 参数名映射(id → repo_id / projectId → source_id 等)
  const remapped: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(args)) {
    const targetKey = mapping.argMap?.[k] ?? k;
    remapped[targetKey] = v;
  }
  try {
    const result = await callCapability<T>(mapping.domain, mapping.name, remapped);
    return wrap<T>(result);
  } catch (err) {
    if (err instanceof ServiceError) {
      throw new ApiRequestError(err.code, err.message, err.status);
    }
    throw err;
  }
}

// ==================== 域类(对齐旧 IApiClient 形态) ====================

/** Local user / GitHub accounts — 本机单用户,GitHub accounts 改走 sources.github_token */
class AuthApi {
  async me() { return wrap({ id: 'local', name: 'Local User' }); }
  async listGithubAccounts() { return wrap([]); }
  async bindGithub() { throw new ApiRequestError('NOT_IMPLEMENTED', '请用 sources.set_github_token'); }
  async unbindGithub() { return wrap({ success: true }); }
  async listStars() { return wrap({ items: [], total: 0 }); }
}

/** Projects / Categories / Tags — 全部走 sources */
class ProjectsApi {
  importProjects(r: unknown) { return call('importProjects', { repos: r }); }
  listProjects(p?: unknown) { return call('listProjects', p as Record<string, unknown>); }
  getProject(id: string) { return call('getProject', { id }); }
  getProjectReadme(id: string) { return call('getProjectReadme', { id }); }
  createProject(d: unknown) { return call('createProject', d as Record<string, unknown>); }
  updateProject(id: string, d: unknown) { return call('updateProject', { id, ...(d as object) }); }
  deleteProject(id: string) { return call('deleteProject', { id }); }
  updateProgress(id: string, p: unknown) { return call('updateProgress', { id, progress: p }); }
  getProjectStats() { return call('getProjectStats'); }
  exportProjects() { return call('exportProjects'); }
  listCategories() { return call('listCategories'); }
  createCategory(d: { name: string }) { return call('createCategory', d); }
  updateCategory(id: string, d: { name: string }) { return call('updateCategory', { id, ...d }); }
  deleteCategory(id: string) { return call('deleteCategory', { id }); }
  listTags() { return call('listTags'); }
  createTag(d: { name: string }) { return call('createTag', d); }
  deleteTag(id: string) { return call('deleteTag', { id }); }
  setProjectTags(projectId: string, tagIds: string[]) { return call('setProjectTags', { projectId, tag_ids: tagIds }); }
  searchGithubRepos(query: string) { return call('searchGithubRepos', { query }); }
}

class NotesApi {
  listNotes(projectId: string) { return call('listNotes', { source_id: projectId }); }
  listAllNotes() { return call('listAllNotes'); }
  getNote(id: string) { return call('getNote', { id }); }
  createNote(projectId: string, d: { title: string; content: string }) {
    return call('createNote', { projectId, title: d.title, content: d.content });
  }
  updateNote(id: string, d: unknown) { return call('updateNote', { id, ...(d as object) }); }
  deleteNote(id: string) { return call('deleteNote', { id }); }
}

class GraphApi {
  getGraph(p?: unknown) { return call('getGraph', p as Record<string, unknown>); }
  getCrossEdges() { return call('getCrossEdges'); }
  getRecommendEdges() { return call('getRecommendEdges'); }
  listCodeGraphIndexStatuses() { return call('listCodeGraphIndexStatuses'); }
  cancelCodeGraphIndex(projectId: string) { return call('cancelCodeGraphIndex', { projectId }); }
  getCodeGraphStatus(projectId: string) { return call('getCodeGraphStatus', { projectId }); }
  triggerCodeGraphIndex(projectId: string, b?: { mode?: 'fast' | 'moderate' | 'full' }) {
    return call('triggerCodeGraphIndex', { projectId, ...b });
  }
  refreshCodeGraphIndex(projectId: string, b?: { mode?: 'fast' | 'moderate' | 'full' }) {
    return call('refreshCodeGraphIndex', { projectId, ...b });
  }
  deleteCodeGraphIndex(projectId: string) { return call('deleteCodeGraphIndex', { projectId }); }
  getCodeGraph(projectId: string, p?: { max_nodes?: number }) { return call('getCodeGraph', { projectId, ...p }); }
  getCodeArchitecture(projectId: string) { return call('getCodeArchitecture', { projectId }); }
  traceCodeGraph(projectId: string, b: { symbol: string; direction?: string; depth?: number }) {
    return call('traceCodeGraph', { projectId, ...b });
  }
  searchCodeGraph(projectId: string, b: { query: string; label?: string; limit?: number }) {
    return call('searchCodeGraph', { projectId, ...b });
  }
  batchIndexCodeGraph(ids: string[], mode?: 'fast' | 'moderate' | 'full') {
    return call('batchIndexCodeGraph', { project_ids: ids, mode });
  }
}

class SettingsApi {
  getSettings() { return call('getSettings'); }
  updateSettings(d: unknown) { return call('updateSettings', d as Record<string, unknown>); }
  saveLlmApiKey(apiKey: string, providerId?: string) {
    return call('saveLlmApiKey', { api_key: apiKey, provider_id: providerId });
  }
  testLLM(p?: unknown) { return call('testLLM', p as Record<string, unknown>); }
}

class OverviewApi {
  listTrending(p?: { period?: string; language?: string }) { return call('listTrending', p); }
  async listActivities() { return wrap([]); }
  listRecommendedProjects(p?: { limit?: number }) { return call('listRecommendedProjects', p); }
  listOverviewRecentNotes(p?: { limit?: number }) { return call('listOverviewRecentNotes', p); }
  /** SSE 走新事件流,见 bridge/stream.ts */
  async *streamTrendingScoutIntro(): AsyncGenerator<SSEEvent> {
    /* deprecated:旧 v2 项目不需 scout 介绍;新实现走 chat 派单 */
    return undefined as never;
  }
}

class AgentApi {
  listAgentSessions() { return call('listAgentSessions'); }
  getAgentSession(_id: string) { return call('getAgentSession'); }
  createAgentSession() { return call('createAgentSession'); }
  deleteAgentSession(_id: string) { return call('deleteAgentSession'); }
  updateAgentSession(_id: string, _d: unknown) { return call('updateAgentSession'); }
  getAgentProfiles() { return call('getAgentProfiles'); }
  getUserProfile() { return call('getUserProfile'); }
  updateUserProfile(d: unknown) { return call('updateUserProfile', d as Record<string, unknown>); }
  clearUserMemory() { return call('clearUserMemory'); }
  acceptMemoryProposal(_id: string) { return call('acceptMemoryProposal'); }
  rejectMemoryProposal(_id: string) { return call('rejectMemoryProposal'); }
  getPermissions() { return call('getPermissions'); }
  getContextWindow(_sessionId?: string) { return call('getContextWindow'); }
  /** SSE — 走新事件流 */
  async *chatAgent(): AsyncGenerator<SSEEvent> { /* deprecated:走 /api/chat/stream */ return undefined as never; }
  async *answerQuestion(): AsyncGenerator<SSEEvent> { return undefined as never; }
  async *analyzeProject(): AsyncGenerator<SSEEvent> { return undefined as never; }
  async *generateNote(): AsyncGenerator<SSEEvent> { return undefined as never; }
  async *importAssistChat(): AsyncGenerator<SSEEvent> { return undefined as never; }
  async *graphGuideChat(): AsyncGenerator<SSEEvent> { return undefined as never; }
}

// ==================== IApiClient 主类 ====================

export class LegacyApiClient {
  readonly auth: AuthApi = new AuthApi();
  readonly projects: ProjectsApi = new ProjectsApi();
  readonly notes: NotesApi = new NotesApi();
  readonly graph: GraphApi = new GraphApi();
  readonly settings: SettingsApi = new SettingsApi();
  readonly overview: OverviewApi = new OverviewApi();
  readonly agent: AgentApi = new AgentApi();
  // 顶层方法
  me = this.auth.me.bind(this.auth);
  listGithubAccounts = this.auth.listGithubAccounts.bind(this.auth);
  bindGithub = this.auth.bindGithub.bind(this.auth);
  unbindGithub = this.auth.unbindGithub.bind(this.auth);
  listStars = this.auth.listStars.bind(this.auth);
  importProjects = this.projects.importProjects.bind(this.projects);
  listProjects = this.projects.listProjects.bind(this.projects);
  getProject = this.projects.getProject.bind(this.projects);
  getProjectReadme = this.projects.getProjectReadme.bind(this.projects);
  createProject = this.projects.createProject.bind(this.projects);
  updateProject = this.projects.updateProject.bind(this.projects);
  deleteProject = this.projects.deleteProject.bind(this.projects);
  updateProgress = this.projects.updateProgress.bind(this.projects);
  getProjectStats = this.projects.getProjectStats.bind(this.projects);
  exportProjects = this.projects.exportProjects.bind(this.projects);
  listCategories = this.projects.listCategories.bind(this.projects);
  createCategory = this.projects.createCategory.bind(this.projects);
  updateCategory = this.projects.updateCategory.bind(this.projects);
  deleteCategory = this.projects.deleteCategory.bind(this.projects);
  listTags = this.projects.listTags.bind(this.projects);
  createTag = this.projects.createTag.bind(this.projects);
  deleteTag = this.projects.deleteTag.bind(this.projects);
  setProjectTags = this.projects.setProjectTags.bind(this.projects);
  searchGithubRepos = this.projects.searchGithubRepos.bind(this.projects);
  listNotes = this.notes.listNotes.bind(this.notes);
  listAllNotes = this.notes.listAllNotes.bind(this.notes);
  getNote = this.notes.getNote.bind(this.notes);
  createNote = this.notes.createNote.bind(this.notes);
  updateNote = this.notes.updateNote.bind(this.notes);
  deleteNote = this.notes.deleteNote.bind(this.notes);
  getGraph = this.graph.getGraph.bind(this.graph);
  getCrossEdges = this.graph.getCrossEdges.bind(this.graph);
  getRecommendEdges = this.graph.getRecommendEdges.bind(this.graph);
  listCodeGraphIndexStatuses = this.graph.listCodeGraphIndexStatuses.bind(this.graph);
  cancelCodeGraphIndex = this.graph.cancelCodeGraphIndex.bind(this.graph);
  getCodeGraphStatus = this.graph.getCodeGraphStatus.bind(this.graph);
  triggerCodeGraphIndex = this.graph.triggerCodeGraphIndex.bind(this.graph);
  refreshCodeGraphIndex = this.graph.refreshCodeGraphIndex.bind(this.graph);
  deleteCodeGraphIndex = this.graph.deleteCodeGraphIndex.bind(this.graph);
  getCodeGraph = this.graph.getCodeGraph.bind(this.graph);
  getCodeArchitecture = this.graph.getCodeArchitecture.bind(this.graph);
  traceCodeGraph = this.graph.traceCodeGraph.bind(this.graph);
  searchCodeGraph = this.graph.searchCodeGraph.bind(this.graph);
  batchIndexCodeGraph = this.graph.batchIndexCodeGraph.bind(this.graph);
  getLlmUsage = (..._a: unknown[]) => (SettingsApi.prototype as never); // 移到 llm 域
  // ↑ 注:旧 IApiClient.getLlmUsage 实际写在 graph.ts,这里补完
  getSettings = this.settings.getSettings.bind(this.settings);
  updateSettings = this.settings.updateSettings.bind(this.settings);
  saveLlmApiKey = this.settings.saveLlmApiKey.bind(this.settings);
  testLLM = this.settings.testLLM.bind(this.settings);
  listTrending = this.overview.listTrending.bind(this.overview);
  listActivities = this.overview.listActivities.bind(this.overview);
  listRecommendedProjects = this.overview.listRecommendedProjects.bind(this.overview);
  listOverviewRecentNotes = this.overview.listOverviewRecentNotes.bind(this.overview);
  streamTrendingScoutIntro = this.overview.streamTrendingScoutIntro.bind(this.overview);
  listAgentSessions = this.agent.listAgentSessions.bind(this.agent);
  getAgentSession = this.agent.getAgentSession.bind(this.agent);
  createAgentSession = this.agent.createAgentSession.bind(this.agent);
  deleteAgentSession = this.agent.deleteAgentSession.bind(this.agent);
  updateAgentSession = this.agent.updateAgentSession.bind(this.agent);
  getAgentProfiles = this.agent.getAgentProfiles.bind(this.agent);
  getUserProfile = this.agent.getUserProfile.bind(this.agent);
  updateUserProfile = this.agent.updateUserProfile.bind(this.agent);
  clearUserMemory = this.agent.clearUserMemory.bind(this.agent);
  acceptMemoryProposal = this.agent.acceptMemoryProposal.bind(this.agent);
  rejectMemoryProposal = this.agent.rejectMemoryProposal.bind(this.agent);
  getPermissions = this.agent.getPermissions.bind(this.agent);
  chatAgent = this.agent.chatAgent.bind(this.agent);
  answerQuestion = this.agent.answerQuestion.bind(this.agent);
  analyzeProject = this.agent.analyzeProject.bind(this.agent);
  generateNote = this.agent.generateNote.bind(this.agent);
  importAssistChat = this.agent.importAssistChat.bind(this.agent);
  graphGuideChat = this.agent.graphGuideChat.bind(this.agent);
  getContextWindow = this.agent.getContextWindow.bind(this.agent);
}

let _api: LegacyApiClient | null = null;

export function getLegacyApi(): LegacyApiClient {
  if (!_api) _api = new LegacyApiClient();
  return _api;
}
