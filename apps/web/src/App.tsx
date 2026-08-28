/** 路由表(中性命名,按域分目录)。重页(图谱/PDF/用量)懒加载,对话首页同步以首屏更快。
 *
 * 历史路径 /projects /agent /graph/projects 保留重定向,避免旧书签落到 404。
 */

import { lazy, Suspense, type ComponentType } from 'react';
import { Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom';
import { AppShell } from '@/shell/AppShell';
import { AgentPage } from '@/pages/agent/AgentPage';
import { NotFound } from '@/shell/NotFound';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { routes } from '@/utils/routes';

function lazyNamed<M extends Record<string, ComponentType | undefined>>(
  loader: () => Promise<M>,
  key: keyof M,
) {
  return lazy(async () => {
    const mod = await loader();
    const Comp = mod[key];
    if (!Comp) throw new Error(`页面导出缺失: ${String(key)}`);
    return { default: Comp };
  });
}

const TeamPage = lazyNamed(() => import('@/pages/team/TeamPage'), 'TeamPage');
const NotesPage = lazyNamed(() => import('@/pages/notes/NotesPage'), 'NotesPage');
const SourcesPage = lazyNamed(() => import('@/pages/sources/SourcesPage'), 'SourcesPage');
const ProjectDetailPage = lazyNamed(
  () => import('@/pages/sources/ProjectDetailPage'),
  'ProjectDetailPage',
);
const DocReader = lazyNamed(() => import('@/pages/sources/DocReader'), 'DocReader');
const PageReader = lazyNamed(() => import('@/pages/sources/PageReader'), 'PageReader');
const GraphPage = lazyNamed(() => import('@/pages/graph/GraphPage'), 'GraphPage');
const CodeGraphPage = lazyNamed(
  () => import('@/pages/code-graph/CodeGraphPage'),
  'CodeGraphPage',
);
const OverviewPage = lazyNamed(() => import('@/pages/overview/OverviewPage'), 'OverviewPage');
const ActivityPage = lazyNamed(() => import('@/pages/activity/ActivityPage'), 'ActivityPage');
const HealthPage = lazyNamed(() => import('@/pages/health/HealthPage'), 'HealthPage');
const UsagePage = lazyNamed(() => import('@/pages/usage/UsagePage'), 'UsagePage');
const SettingsPage = lazyNamed(() => import('@/pages/settings/SettingsPage'), 'SettingsPage');

function RedirectKeepSearch({ to }: { to: string }) {
  const loc = useLocation();
  return <Navigate to={{ pathname: to, search: loc.search, hash: loc.hash }} replace />;
}

function RedirectProject() {
  const { id } = useParams();
  return <Navigate to={id ? routes.sourceRepo(id) : routes.sources} replace />;
}

function RedirectCodeGraph() {
  const { id } = useParams();
  return <Navigate to={id ? routes.codeGraph(id) : routes.graph} replace />;
}

function PageFallback() {
  return <LoadingSpinner fullScreen label="载入页面…" />;
}

export function App() {
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<AgentPage />} />
          <Route path="chat" element={<AgentPage />} />
          <Route path="chat/:sessionId" element={<AgentPage />} />
          <Route path="agent" element={<RedirectKeepSearch to={routes.chat} />} />
          <Route path="team" element={<TeamPage />} />
          <Route path="notes" element={<NotesPage />} />
          <Route path="sources" element={<SourcesPage />} />
          <Route path="sources/repo/:id" element={<ProjectDetailPage />} />
          <Route path="sources/doc/:id" element={<DocReader />} />
          <Route path="sources/web/:id" element={<PageReader />} />
          <Route path="sources/:id" element={<ProjectDetailPage />} />
          <Route path="projects" element={<Navigate to={routes.sources} replace />} />
          <Route path="projects/:id" element={<RedirectProject />} />
          <Route path="graph" element={<GraphPage />} />
          <Route path="graph/projects/:id" element={<RedirectCodeGraph />} />
          <Route path="code-graph" element={<CodeGraphPage />} />
          <Route path="code-graph/:id" element={<CodeGraphPage />} />
          <Route path="overview" element={<OverviewPage />} />
          <Route path="activity" element={<ActivityPage />} />
          <Route path="system/health" element={<HealthPage />} />
          <Route path="usage" element={<UsagePage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
