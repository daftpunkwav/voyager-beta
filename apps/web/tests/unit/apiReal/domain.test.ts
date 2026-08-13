/**
 * api/real ????????? ?? ??? ??4.2.17
 *   1. RealApiClient ???? IApiClient ???????(????? + ???????)
 *   2. 7 ????????????????
 *   3. ??��????????????? domain ????(fetch mocked)
 *
 * ?:RealApiClient ????��????? this.{auth,projects,...} ?????
 * ?????? function ????(??��????????��??????????,????????? method),
 * ??????????? ?? ?????? spy ???????????????
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { IApiClient } from '@/api/client';
import { RealApiClient } from '@/api/real';
import type { AgentApi } from '@/api/real/domain/agent';
import type { AuthApi } from '@/api/real/domain/auth';
import type { GraphApi } from '@/api/real/domain/graph';
import type { NotesApi } from '@/api/real/domain/notes';
import type { OverviewApi } from '@/api/real/domain/overview';
import type { ProjectsApi } from '@/api/real/domain/projects';
import type { SettingsApi } from '@/api/real/domain/settings';

function okJson<T>(body: T): Response {
  return new Response(JSON.stringify({ data: body, meta: { ts: 1 } }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('RealApiClient domain split (??4.2.17)', () => {
  it('implements IApiClient', () => {
    // ?????:???��?????? = implements ????,???? TS ????
    const client: IApiClient = new RealApiClient();
    expect(client).toBeInstanceOf(RealApiClient);
  });

  it('exposes seven domain sub-clients with concrete types', () => {
    const client = new RealApiClient();
    const _auth: AuthApi = client.auth;
    const _projects: ProjectsApi = client.projects;
    const _notes: NotesApi = client.notes;
    const _graph: GraphApi = client.graph;
    const _settings: SettingsApi = client.settings;
    const _overview: OverviewApi = client.overview;
    const _agent: AgentApi = client.agent;
    expect(_auth).toBe(client.auth);
    expect(_projects).toBe(client.projects);
    expect(_notes).toBe(client.notes);
    expect(_graph).toBe(client.graph);
    expect(_settings).toBe(client.settings);
    expect(_overview).toBe(client.overview);
    expect(_agent).toBe(client.agent);
  });

  it('exposes all IApiClient methods as functions', () => {
    const client = new RealApiClient();
    const methodNames: (keyof IApiClient)[] = [
      'me',
      'listGithubAccounts', 'bindGithub', 'unbindGithub', 'listStars',
      'importProjects', 'listProjects', 'getProject', 'getProjectReadme',
      'createProject', 'updateProject', 'deleteProject', 'updateProgress',
      'getProjectStats', 'exportProjects',
      'listCategories', 'createCategory', 'updateCategory', 'deleteCategory',
      'listTags', 'createTag', 'deleteTag', 'setProjectTags',
      'listNotes', 'listAllNotes', 'getNote', 'createNote', 'updateNote', 'deleteNote',
      'getGraph', 'searchGithubRepos',
      'getSettings', 'updateSettings', 'saveLlmApiKey', 'testLLM',
      'listTrending', 'streamTrendingScoutIntro', 'listActivities',
      'listRecommendedProjects', 'listOverviewRecentNotes',
      'listAgentSessions', 'getAgentSession', 'createAgentSession',
      'deleteAgentSession', 'updateAgentSession', 'getAgentProfiles',
      'chatAgent', 'answerQuestion', 'analyzeProject', 'generateNote',
      'getContextWindow', 'importAssistChat', 'graphGuideChat',
      'getUserProfile', 'updateUserProfile', 'clearUserMemory',
      'acceptMemoryProposal', 'rejectMemoryProposal', 'getPermissions',
    ];
    expect(methodNames.length).toBe(59);
    for (const name of methodNames) {
      const fn = (client as unknown as Record<string, unknown>)[name as string];
      expect(typeof fn).toBe('function');
    }
  });

  it('??? me ��?????(???? /user/me + GET)', async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        okJson({
          id: 'local',
          username: 'local',
          github_bound: false,
          created_at: '2026-01-01T00:00:00Z',
        })
      )
    );
    const originalFetch = globalThis.fetch;
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    try {
      const client = new RealApiClient();
      await client.me();
      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toContain('/user/me');
      expect(init.method === undefined || (init.method as string).toUpperCase() === 'GET').toBe(true);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('??��??? Api ???????????????????(spy ???)', async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        okJson({
          id: 'local',
          username: 'local',
          github_bound: false,
          created_at: '2026-01-01T00:00:00Z',
        })
      )
    );
    const originalFetch = globalThis.fetch;
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    try {
      const client = new RealApiClient();
      const spy = vi.spyOn(client.auth, 'me');
      await client.me();
      expect(spy).toHaveBeenCalledTimes(1);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('??? listProjects ��?????????????', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(okJson({ items: [], total: 0, page: 1, page_size: 10 })));
    const originalFetch = globalThis.fetch;
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    try {
      const client = new RealApiClient();
      await client.listProjects({ search: 'demo', language: 'TypeScript' });
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toContain('/projects/');
      expect(url).toContain('search=demo');
      expect(url).toContain('language=TypeScript');
      // GET ????? fetch ??? method ? undefined,?????????
      expect(init.method === undefined || (init.method as string).toUpperCase() === 'GET').toBe(true);
      expect(init.body).toBeUndefined();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('??? getAgentSession ?? AgentApi ???????? fetch', async () => {
    const detailData = {
      id: 7,
      agent: 'hub',
      title: 'demo',
      project_id: null,
      project_ids: [],
      source: 'chat',
      messages: [],
    };
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(okJson(detailData)));
    const originalFetch = globalThis.fetch;
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    try {
      const client = new RealApiClient();
      const res = await client.getAgentSession('7');
      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url] = fetchMock.mock.calls[0] as [string];
      expect(url).toContain('/agent/sessions/7');
      // ?????? id ?? Number ?? String ????
      expect(typeof res.data.id).toBe('string');
      expect(res.data.id).toBe('7');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });
});
