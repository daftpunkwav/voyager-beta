/**
 * RealApiClient �� ��ʵ��� IApiClient ʵ��,��ҵ�����ֺ�ͨ�� 7 �� Api ����ί�� (��4.2.17)
 *
 * ί��(���Ǽ̳�)�ĺô�:
 *   1. ÿ���������ά�����ɵ���;��������� 7 �� readonly ���ֶΡ�
 *   2. ���Ͱ�ȫ:methods ֱ��ת���� `this.{auth,projects,...}`,
 *      TS �ڱ�������֤ IApiClient ȫ��ǩ��(���� implements ʧ��)��
 *   3. ���� IApiClient:`import { RealApiClient } from '@/api/real'` ·����
 *      `new RealApiClient()` 实例；`getApi().me()` 等走全局客户端。
 */
import type { IApiClient } from '@/api/client';
import {
  AgentApi,
  AuthApi,
  GraphApi,
  NotesApi,
  OverviewApi,
  ProjectsApi,
  SettingsApi,
} from './domain';
import { apiRequest, apiSSE } from './http';

export class RealApiClient implements IApiClient {
  readonly auth: AuthApi;
  readonly projects: ProjectsApi;
  readonly notes: NotesApi;
  readonly graph: GraphApi;
  readonly settings: SettingsApi;
  readonly overview: OverviewApi;
  readonly agent: AgentApi;

  constructor() {
    const ctx = { apiRequest, apiSSE };
    this.auth = new AuthApi(ctx);
    this.projects = new ProjectsApi(ctx);
    this.notes = new NotesApi(ctx);
    this.graph = new GraphApi(ctx);
    this.settings = new SettingsApi(ctx);
    this.overview = new OverviewApi(ctx);
    this.agent = new AgentApi(ctx);
  }

  // ------- Local user / GitHub -------
  me() { return this.auth.me(); }
  listGithubAccounts() { return this.auth.listGithubAccounts(); }
  bindGithub(p: Parameters<IApiClient['bindGithub']>[0]) { return this.auth.bindGithub(p); }
  unbindGithub(id: string) { return this.auth.unbindGithub(id); }
  listStars(p?: Parameters<IApiClient['listStars']>[0]) { return this.auth.listStars(p); }

  // ------- Projects / Categories / Tags (18) -------
  importProjects(r: Parameters<IApiClient['importProjects']>[0]) { return this.projects.importProjects(r); }
  listProjects(p?: Parameters<IApiClient['listProjects']>[0]) { return this.projects.listProjects(p); }
  getProject(id: string) { return this.projects.getProject(id); }
  getProjectReadme(id: string) { return this.projects.getProjectReadme(id); }
  createProject(d: Parameters<IApiClient['createProject']>[0]) { return this.projects.createProject(d); }
  updateProject(id: string, d: Parameters<IApiClient['updateProject']>[1]) { return this.projects.updateProject(id, d); }
  deleteProject(id: string) { return this.projects.deleteProject(id); }
  updateProgress(id: string, p: Parameters<IApiClient['updateProgress']>[1]) { return this.projects.updateProgress(id, p); }
  getProjectStats() { return this.projects.getProjectStats(); }
  exportProjects() { return this.projects.exportProjects(); }
  listCategories() { return this.projects.listCategories(); }
  createCategory(d: Parameters<IApiClient['createCategory']>[0]) { return this.projects.createCategory(d); }
  updateCategory(id: string, d: Parameters<IApiClient['updateCategory']>[1]) { return this.projects.updateCategory(id, d); }
  deleteCategory(id: string) { return this.projects.deleteCategory(id); }
  listTags() { return this.projects.listTags(); }
  createTag(d: Parameters<IApiClient['createTag']>[0]) { return this.projects.createTag(d); }
  deleteTag(id: string) { return this.projects.deleteTag(id); }
  setProjectTags(p: string, t: string[]) { return this.projects.setProjectTags(p, t); }

  // ------- Notes (6) -------
  listNotes(p: string) { return this.notes.listNotes(p); }
  listAllNotes() { return this.notes.listAllNotes(); }
  getNote(id: string) { return this.notes.getNote(id); }
  createNote(p: string, d: Parameters<IApiClient['createNote']>[1]) { return this.notes.createNote(p, d); }
  updateNote(id: string, d: Parameters<IApiClient['updateNote']>[1]) { return this.notes.updateNote(id, d); }
  deleteNote(id: string) { return this.notes.deleteNote(id); }

  // ------- Graph / Search -------
  getGraph(p?: Parameters<IApiClient['getGraph']>[0]) { return this.graph.getGraph(p); }
  getCrossEdges() { return this.graph.getCrossEdges(); }
  getRecommendEdges() { return this.graph.getRecommendEdges(); }
  listCodeGraphIndexStatuses() { return this.graph.listCodeGraphIndexStatuses(); }
  cancelCodeGraphIndex(id: string) { return this.graph.cancelCodeGraphIndex(id); }
  getCodeGraphStatus(id: string) { return this.graph.getCodeGraphStatus(id); }
  triggerCodeGraphIndex(id: string, b?: Parameters<IApiClient['triggerCodeGraphIndex']>[1]) {
    return this.graph.triggerCodeGraphIndex(id, b);
  }
  refreshCodeGraphIndex(id: string, b?: Parameters<IApiClient['refreshCodeGraphIndex']>[1]) {
    return this.graph.refreshCodeGraphIndex(id, b);
  }
  deleteCodeGraphIndex(id: string) { return this.graph.deleteCodeGraphIndex(id); }
  getCodeGraph(id: string, p?: Parameters<IApiClient['getCodeGraph']>[1]) {
    return this.graph.getCodeGraph(id, p);
  }
  getCodeArchitecture(id: string) { return this.graph.getCodeArchitecture(id); }
  traceCodeGraph(id: string, b: Parameters<IApiClient['traceCodeGraph']>[1]) {
    return this.graph.traceCodeGraph(id, b);
  }
  searchCodeGraph(id: string, b: Parameters<IApiClient['searchCodeGraph']>[1]) {
    return this.graph.searchCodeGraph(id, b);
  }
  searchGithubRepos(q: string) { return this.graph.searchGithubRepos(q); }
  batchIndexCodeGraph(ids: string[], mode?: Parameters<IApiClient['batchIndexCodeGraph']>[1]) {
    return this.graph.batchIndexCodeGraph(ids, mode);
  }
  getLlmUsage(days?: Parameters<IApiClient['getLlmUsage']>[0]) { return this.graph.getLlmUsage(days); }

  // ------- Settings (4) -------
  getSettings() { return this.settings.getSettings(); }
  updateSettings(d: Parameters<IApiClient['updateSettings']>[0]) { return this.settings.updateSettings(d); }
  saveLlmApiKey(k: string, providerId?: string) {
    return this.settings.saveLlmApiKey(k, providerId);
  }
  testLLM(p?: Parameters<IApiClient['testLLM']>[0]) { return this.settings.testLLM(p); }

  // ------- Overview (5) -------
  listTrending(p?: Parameters<IApiClient['listTrending']>[0]) { return this.overview.listTrending(p); }
  streamTrendingScoutIntro(p: Parameters<IApiClient['streamTrendingScoutIntro']>[0], s?: Parameters<IApiClient['streamTrendingScoutIntro']>[1]) { return this.overview.streamTrendingScoutIntro(p, s); }
  listActivities() { return this.overview.listActivities(); }
  listRecommendedProjects(p?: Parameters<IApiClient['listRecommendedProjects']>[0]) { return this.overview.listRecommendedProjects(p); }
  listOverviewRecentNotes(p?: Parameters<IApiClient['listOverviewRecentNotes']>[0]) { return this.overview.listOverviewRecentNotes(p); }

  // ------- Agent / Profile / Memory / Permissions (19) -------
  listAgentSessions() { return this.agent.listAgentSessions(); }
  getAgentSession(id: string) { return this.agent.getAgentSession(id); }
  createAgentSession() { return this.agent.createAgentSession(); }
  deleteAgentSession(id: string) { return this.agent.deleteAgentSession(id); }
  updateAgentSession(id: string, d: Parameters<IApiClient['updateAgentSession']>[1]) { return this.agent.updateAgentSession(id, d); }
  getAgentProfiles() { return this.agent.getAgentProfiles(); }
  chatAgent(s: string, m: string, sig?: Parameters<IApiClient['chatAgent']>[2]) { return this.agent.chatAgent(s, m, sig); }
  answerQuestion(s: string, q: string, a: Parameters<IApiClient['answerQuestion']>[2], sig?: Parameters<IApiClient['answerQuestion']>[3], sk?: Parameters<IApiClient['answerQuestion']>[4]) { return this.agent.answerQuestion(s, q, a, sig, sk); }
  analyzeProject(id: string, a?: Parameters<IApiClient['analyzeProject']>[1], sig?: Parameters<IApiClient['analyzeProject']>[2]) { return this.agent.analyzeProject(id, a, sig); }
  generateNote(id: string, p?: Parameters<IApiClient['generateNote']>[1], sig?: Parameters<IApiClient['generateNote']>[2]) { return this.agent.generateNote(id, p, sig); }
  getContextWindow(s?: string | null) { return this.agent.getContextWindow(s); }
  importAssistChat(m: string, c: Parameters<IApiClient['importAssistChat']>[1], sig?: Parameters<IApiClient['importAssistChat']>[2]) { return this.agent.importAssistChat(m, c, sig); }
  graphGuideChat(m: string, c?: Parameters<IApiClient['graphGuideChat']>[1], sig?: Parameters<IApiClient['graphGuideChat']>[2]) { return this.agent.graphGuideChat(m, c, sig); }
  getUserProfile() { return this.agent.getUserProfile(); }
  updateUserProfile(d: Parameters<IApiClient['updateUserProfile']>[0]) { return this.agent.updateUserProfile(d); }
  clearUserMemory() { return this.agent.clearUserMemory(); }
  acceptMemoryProposal(id: string) { return this.agent.acceptMemoryProposal(id); }
  rejectMemoryProposal(id: string) { return this.agent.rejectMemoryProposal(id); }
  getPermissions() { return this.agent.getPermissions(); }
}
