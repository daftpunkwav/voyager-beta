/** 数据门面实现层(不由业务代码直接引用)— 84 个方法内部全部走 callCapability,
 * 保留旧调用形态(命名中性,domain 归类为 agent / source / note / graph / setting / usage / system)。
 *
 * 设计目的:让已迁移的旧 page / hooks / components 在不修改源码的情况下,
 * 通过本层接进 capability 框架(§2.1 一份 Action 模型)。
 *
 * 命名约定:
 *  - 域:旧 IApiClient 的 7 个域(auth/projects/notes/graph/settings/overview/agent)
 *    → 本仓库的 capability 域(notes/llm/graph/sources/browser/code-exec/settings/agent)
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
 *  - 业务代码一律经 @/api/client 门面访问(ESLint no-restricted-imports 固化);
 *    少数只读能力可直用 @/bridge/client 的 callCapability。
 *  - secret 边界(API key 等)只允许 USER actor 写,本层不绕开(直接转发到能力层)。
 *  - getApi() 单例在 app 启动时懒初始化,旧 store / hook 仍调 getApi()(经桥接,功能等价)。
 */

import { callCapability, ServiceError, uploadFile } from './client';

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
  getGraph: { domain: 'graph', name: 'l0_view' },
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
  enqueueL0: { domain: 'graph', name: 'enqueue_l0' },

  // ---- settings ----
  getSettings: { domain: 'settings', name: 'get_settings' },
  updateSettings: { domain: 'settings', name: 'set_setting' },
  saveLlmApiKey: { domain: 'llm', name: 'set_api_key' },
  testLLM: { domain: 'llm', name: 'test_connection' },

  // ---- llm usage ----
  getLlmUsage: { domain: 'llm', name: 'get_usage_stats' },

  // ---- agent(状态 / profile / memory) ----
  // 会话 CRUD 已废弃(单时间线,§6.3):见 AgentApi 内的显式抛错,不再静默映射
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
  /** GitHub stars(真桥接:list_starred_repos;未配 token 时后端限流报错引导设置页) */
  listStars(username: string, limit = 100) {
    return callCapability('sources', 'list_starred_repos', { username, limit })
      .then((items) => wrap({ items, total: Array.isArray(items) ? items.length : 0 }))
      .catch((err) => {
        if (err instanceof ServiceError) throw new ApiRequestError(err.code, err.message, err.status);
        throw err;
      });
  }
  setGithubToken(token: string) {
    return callCapability('sources', 'set_github_token', { token })
      .then((r) => wrap(r))
      .catch((err) => {
        if (err instanceof ServiceError) throw new ApiRequestError(err.code, err.message, err.status);
        throw err;
      });
  }
}

/** 统一资源库(repo/doc/web 三类资源 + 跨类型资源流)。 */
class SourcesApi {
  // ---- 仓库(repo) ----
  importRepo(url: string, category = '') {
    return callCapability('sources', 'import_repo', { url, category }).then((r) => wrap(r));
  }

  // ---- 跨类型 ----
  listSources(p?: { kind?: string; status?: string; tag?: string; query?: string; sort?: string; desc?: boolean; limit?: number }) {
    return callCapability('sources', 'list_sources', p ?? {}).then((r) => wrap(r));
  }
  searchSources(query: string, kind = '', limit = 20) {
    return callCapability('sources', 'search_sources', { query, kind, limit }).then((r) => wrap(r));
  }
  sourcesStats() { return callCapability('sources', 'sources_stats', {}).then((r) => wrap(r)); }

  // ---- 文档(doc) ----
  uploadDocument(file: File, meta: { title?: string; tags?: string[]; category?: string } = {}) {
    // 组合流:上传落盘 → 能力入库(两步都必须,缺一不可)
    return uploadFile(file).then(({ file_path, filename }) =>
      callCapability('sources', 'add_document', {
        file_path, title: meta.title || filename, tags: meta.tags, category: meta.category,
      }).then((r) => wrap(r)));
  }
  addDocument(filePath: string, meta: { title?: string; tags?: string[]; category?: string } = {}) {
    return callCapability('sources', 'add_document', { file_path: filePath, ...meta }).then((r) => wrap(r));
  }
  listDocuments(p?: { status?: string; tag?: string; query?: string; sort?: string; desc?: boolean; limit?: number }) {
    return callCapability('sources', 'list_documents', p ?? {}).then((r) => wrap(r));
  }
  getDocument(docId: string) {
    return callCapability('sources', 'get_document', { doc_id: docId }).then((r) => wrap(r));
  }
  getDocSection(docId: string, sectionNo: number) {
    return callCapability('sources', 'get_doc_section', { doc_id: docId, section_no: sectionNo }).then((r) => wrap(r));
  }
  searchDocuments(query: string, limit = 20) {
    return callCapability('sources', 'search_documents', { query, limit }).then((r) => wrap(r));
  }
  setDocumentMeta(docId: string, d: { title?: string; category?: string; tags?: string[]; progress?: string; note?: string }) {
    return callCapability('sources', 'set_document_meta', { doc_id: docId, ...d }).then((r) => wrap(r));
  }
  removeDocument(docId: string) {
    return callCapability('sources', 'remove_document', { doc_id: docId }).then((r) => wrap(r));
  }
  /** 文档原文件下载 URL(内联预览,如 PDF 直开) */
  docFileUrl(docId: string) { return `/api/sources/files/doc/${docId}`; }

  // ---- 网页剪藏(web) ----
  saveUrl(url: string, meta: { title?: string; tags?: string[]; category?: string } = {}) {
    return callCapability('sources', 'save_url', { url, ...meta }).then((r) => wrap(r));
  }
  addPage(d: { title: string; content?: string; url?: string; tags?: string[] }) {
    return callCapability('sources', 'add_page', d).then((r) => wrap(r));
  }
  listPages(p?: { query?: string; tag?: string; limit?: number }) {
    return callCapability('sources', 'list_pages', p ?? {}).then((r) => wrap(r));
  }
  getPage(pageId: string) {
    return callCapability('sources', 'get_page', { page_id: pageId }).then((r) => wrap(r));
  }
  setPageMeta(pageId: string, d: { title?: string; tags?: string[]; category?: string }) {
    return callCapability('sources', 'set_page_meta', { page_id: pageId, ...d }).then((r) => wrap(r));
  }
  removePage(pageId: string) {
    return callCapability('sources', 'remove_page', { page_id: pageId }).then((r) => wrap(r));
  }
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

/** 笔记域:既有 6 个旧形态方法 + 直桥能力(addAsset/回收站/版本/标签/导入导出)。 */
class NotesApi {
  listNotes(projectId: string) { return call('listNotes', { source_id: projectId }); }
  listAllNotes() { return call('listAllNotes'); }
  getNote(id: string) { return call('getNote', { id }); }
  createNote(projectId: string, d: { title: string; content: string }) {
    return call('createNote', { projectId, title: d.title, content: d.content });
  }
  updateNote(id: string, d: unknown) { return call('updateNote', { id, ...(d as object) }); }
  deleteNote(id: string) { return call('deleteNote', { id }); }

  // ---- 直桥(notes 能力名即 capability 名;用户与 agent 同权) ----
  private async cap<T>(name: string, args: Record<string, unknown> = {}): Promise<ApiResponse<T>> {
    try {
      return wrap<T>(await callCapability('notes', name, args));
    } catch (err) {
      if (err instanceof ServiceError) throw new ApiRequestError(err.code, err.message, err.status);
      throw err;
    }
  }
  /** 服务端搜索(list_notes 的 query:标题+正文 LIKE,命中窗口摘要) */
  searchNotes(query: string, extra: { tag?: string; state?: string; sort?: string; limit?: number } = {}) {
    return this.cap('list_notes', { query, ...extra });
  }
  listTags() { return this.cap('list_tags'); }
  notesStats() { return this.cap('notes_stats'); }
  getBacklinks(id: string) { return this.cap('get_backlinks', { note_id: id }); }
  getNoteToc(id: string) { return this.cap('get_note_toc', { note_id: id }); }
  restoreNote(id: string) { return this.cap('restore_note', { note_id: id }); }
  purgeNote(id: string) { return this.cap('purge_note', { note_id: id }); }
  emptyTrash() { return this.cap('empty_trash'); }
  listVersions(id: string) { return this.cap('list_versions', { note_id: id }); }
  readVersion(id: string, version: number) {
    return this.cap('read_version', { note_id: id, version });
  }
  restoreVersion(id: string, version: number) {
    return this.cap('restore_version', { note_id: id, version });
  }
  renameTag(oldName: string, newName: string) {
    return this.cap('rename_tag', { old: oldName, new: newName });
  }
  linkNote(id: string, sourceId: string | null) {
    return this.cap('link_note', { note_id: id, source_id: sourceId });
  }
  importNote(filePath: string, meta: { title?: string; tags?: string[] } = {}) {
    return this.cap('import_note', { file_path: filePath, ...meta });
  }
  exportNote(id: string) { return this.cap('export_note', { note_id: id }); }
  batchNotes(ids: string[], action: string) {
    return this.cap('batch_notes', { ids, action });
  }
  addAsset(filePath: string, filename = '', noteId = '') {
    return this.cap('add_asset', { file_path: filePath, filename, note_id: noteId });
  }
}

class GraphApi {
  /** L0 视图:kinds 选资源种类子集([]/undefined=全部) */
  getGraph(p?: { kinds?: string[]; limit?: number }) {
    return call('getGraph', p as Record<string, unknown> | undefined);
  }
  /** L0 关联分析入队(kinds ⊆ repo/doc/web) */
  enqueueL0(kinds: string[], priority = 100) {
    return call('enqueueL0', { kinds, priority });
  }
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

/** 会话 CRUD 已废弃:新架构是单时间线(gateway 不建会话表,§6.3),
 *  聊天史即事件日志;发消息走 POST /api/chat/messages,历史走 GET 同路径,
 *  实时经 bridge/stream 订阅 SSE。禁止再映射到 agent.list_subagents 冒充会话。 */
function deprecatedSessionApi(method: string): never {
  throw new ApiRequestError(
    'NOT_IMPLEMENTED',
    `${method} 已废弃:会话 CRUD 不再存在,聊天走 /api/chat/messages 与 /api/chat/stream`,
  );
}

class AgentApi {
  listAgentSessions() { deprecatedSessionApi('listAgentSessions'); }
  getAgentSession(_id: string) { deprecatedSessionApi('getAgentSession'); }
  createAgentSession() { deprecatedSessionApi('createAgentSession'); }
  deleteAgentSession(_id: string) { deprecatedSessionApi('deleteAgentSession'); }
  updateAgentSession(_id: string, _d: unknown) { deprecatedSessionApi('updateAgentSession'); }
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
}

// ==================== IApiClient 主类 ====================

export class LegacyApiClient {
  readonly auth: AuthApi = new AuthApi();
  readonly sources: SourcesApi = new SourcesApi();
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
  setGithubToken = this.auth.setGithubToken.bind(this.auth);
  importRepo = this.sources.importRepo.bind(this.sources);
  listSources = this.sources.listSources.bind(this.sources);
  searchSources = this.sources.searchSources.bind(this.sources);
  sourcesStats = this.sources.sourcesStats.bind(this.sources);
  uploadDocument = this.sources.uploadDocument.bind(this.sources);
  addDocument = this.sources.addDocument.bind(this.sources);
  listDocuments = this.sources.listDocuments.bind(this.sources);
  getDocument = this.sources.getDocument.bind(this.sources);
  getDocSection = this.sources.getDocSection.bind(this.sources);
  searchDocuments = this.sources.searchDocuments.bind(this.sources);
  setDocumentMeta = this.sources.setDocumentMeta.bind(this.sources);
  removeDocument = this.sources.removeDocument.bind(this.sources);
  docFileUrl = this.sources.docFileUrl.bind(this.sources);
  saveUrl = this.sources.saveUrl.bind(this.sources);
  addPage = this.sources.addPage.bind(this.sources);
  listPages = this.sources.listPages.bind(this.sources);
  getPage = this.sources.getPage.bind(this.sources);
  setPageMeta = this.sources.setPageMeta.bind(this.sources);
  removePage = this.sources.removePage.bind(this.sources);
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
  searchNotes = this.notes.searchNotes.bind(this.notes);
  listNoteTags = this.notes.listTags.bind(this.notes);
  notesStats = this.notes.notesStats.bind(this.notes);
  getBacklinks = this.notes.getBacklinks.bind(this.notes);
  getNoteToc = this.notes.getNoteToc.bind(this.notes);
  restoreNote = this.notes.restoreNote.bind(this.notes);
  purgeNote = this.notes.purgeNote.bind(this.notes);
  emptyTrash = this.notes.emptyTrash.bind(this.notes);
  listVersions = this.notes.listVersions.bind(this.notes);
  readVersion = this.notes.readVersion.bind(this.notes);
  restoreVersion = this.notes.restoreVersion.bind(this.notes);
  renameNoteTag = this.notes.renameTag.bind(this.notes);
  linkNote = this.notes.linkNote.bind(this.notes);
  importNote = this.notes.importNote.bind(this.notes);
  exportNote = this.notes.exportNote.bind(this.notes);
  batchNotes = this.notes.batchNotes.bind(this.notes);
  addAsset = this.notes.addAsset.bind(this.notes);
  listAllNotes = this.notes.listAllNotes.bind(this.notes);
  getNote = this.notes.getNote.bind(this.notes);
  createNote = this.notes.createNote.bind(this.notes);
  updateNote = this.notes.updateNote.bind(this.notes);
  deleteNote = this.notes.deleteNote.bind(this.notes);
  getGraph = this.graph.getGraph.bind(this.graph);
  enqueueL0 = this.graph.enqueueL0.bind(this.graph);
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
  getLlmUsage = (days?: number) => call('getLlmUsage', { days: days ?? 30 });
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
  getContextWindow = this.agent.getContextWindow.bind(this.agent);
}

let _api: LegacyApiClient | null = null;

export function getLegacyApi(): LegacyApiClient {
  if (!_api) _api = new LegacyApiClient();
  return _api;
}
