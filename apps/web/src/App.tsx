/** 路由表(中性命名,按域分目录):
 *   /                  pages/agent/AgentPage         —— Agent Chat 主页
 *   /chat/:sessionId   pages/agent/AgentPage         —— 特定会话(同一组件,按 useParams 切换)
 *   /team              pages/team/TeamPage            —— 团队/Persona
 *   /notes             pages/notes/NotesPage
 *   /sources           pages/sources/ProjectsPage     —— 资源库(原项目库)
 *   /sources/:id       pages/sources/ProjectDetailPage
 *   /graph             pages/graph/GraphPage
 *   /code-graph/:id    pages/code-graph/CodeGraphPage
 *   /overview          pages/overview/OverviewPage    —— 总览(原首页,挪到导航栏)
 *   /activity          pages/activity/ActivityPage    —— 活动流
 *   /system/health     pages/health/HealthPage        —— 服务健康
 *   /usage             pages/usage/UsagePage
 *   /settings          pages/settings/SettingsPage
 *
 * 每个 page 目录自包含(§10.1 页面即模块);跨 page 共享只经 bridge/contracts/基础 UI。
 */

import { Route, Routes } from 'react-router-dom';
import { AppShell } from '@/shell/AppShell';
import { AgentPage } from '@/pages/agent/AgentPage';
import { TeamPage } from '@/pages/team/TeamPage';
import { NotesPage } from '@/pages/notes/NotesPage';
import { SourcesPage } from '@/pages/sources/SourcesPage';
import { ProjectDetailPage } from '@/pages/sources/ProjectDetailPage';
import { DocReader } from '@/pages/sources/DocReader';
import { PageReader } from '@/pages/sources/PageReader';
import { GraphPage } from '@/pages/graph/GraphPage';
import { CodeGraphPage } from '@/pages/code-graph/CodeGraphPage';
import { OverviewPage } from '@/pages/overview/OverviewPage';
import { ActivityPage } from '@/pages/activity/ActivityPage';
import { HealthPage } from '@/pages/health/HealthPage';
import { UsagePage } from '@/pages/usage/UsagePage';
import { SettingsPage } from '@/pages/settings/SettingsPage';

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<AgentPage />} />
        <Route path="chat" element={<AgentPage />} />
        <Route path="chat/:sessionId" element={<AgentPage />} />
        <Route path="team" element={<TeamPage />} />
        <Route path="notes" element={<NotesPage />} />
        <Route path="sources" element={<SourcesPage />} />
        <Route path="sources/repo/:id" element={<ProjectDetailPage />} />
        <Route path="sources/doc/:id" element={<DocReader />} />
        <Route path="sources/web/:id" element={<PageReader />} />
        <Route path="sources/:id" element={<ProjectDetailPage />} />
        <Route path="graph" element={<GraphPage />} />
        <Route path="code-graph" element={<CodeGraphPage />} />
        <Route path="code-graph/:id" element={<CodeGraphPage />} />
        <Route path="overview" element={<OverviewPage />} />
        <Route path="activity" element={<ActivityPage />} />
        <Route path="system/health" element={<HealthPage />} />
        <Route path="usage" element={<UsagePage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<OverviewPage />} />
      </Route>
    </Routes>
  );
}
