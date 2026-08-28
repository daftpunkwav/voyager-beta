/** 前端路由单一来源。历史别名 /projects /agent /graph/projects 由 App 重定向。 */

export const routes = {
  chat: '/',
  chatSession: (id: string) => `/chat/${encodeURIComponent(id)}`,
  team: '/team',
  notes: '/notes',
  note: (id: string, project?: string) => {
    const q = new URLSearchParams({ note: id });
    if (project) q.set('project', project);
    return `/notes?${q.toString()}`;
  },
  sources: '/sources',
  sourceRepo: (id: string) => `/sources/repo/${encodeURIComponent(id)}`,
  sourceDoc: (id: string) => `/sources/doc/${encodeURIComponent(id)}`,
  sourceWeb: (id: string) => `/sources/web/${encodeURIComponent(id)}`,
  /** 图谱节点 / 活动条目按 kind 落到资源详情。 */
  sourceOf: (kind: string | undefined, id: string) => {
    if (kind === 'doc') return `/sources/doc/${encodeURIComponent(id)}`;
    if (kind === 'web') return `/sources/web/${encodeURIComponent(id)}`;
    return `/sources/repo/${encodeURIComponent(id)}`;
  },
  graph: '/graph',
  codeGraph: (id: string) => `/code-graph/${encodeURIComponent(id)}`,
  overview: '/overview',
  activity: '/activity',
  health: '/system/health',
  usage: '/usage',
  settings: '/settings',
} as const;
