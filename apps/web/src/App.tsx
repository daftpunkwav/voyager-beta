/** 路由表(中性命名):
 *   /                  AgentPage    —— Agent Chat 主页
 *   /chat/:sessionId   AgentPage    —— 特定会话(同一组件,按 useParams 切换)
 *   /team              TeamPage      —— 团队/Persona
 *   /notes             NotesPage
 *   /sources           ProjectsPage  —— 资源库(原项目库)
 *   /sources/:id       ProjectDetailPage
 *   /graph             GraphPage
 *   /code-graph/:id    CodeGraphPage
 *   /overview          OverviewPage  —— 总览(原首页,挪到导航栏)
 *   /activity          ActivityPage  —— 活动流
 *   /system/health     HealthPage    —— 服务健康
 *   /usage             UsagePage
 *   /settings          SettingsPage
 */

import { Route, Routes } from 'react-router-dom';
import { AppShell } from '@/shell/AppShell';
import { AgentPage } from '@/pages/AgentPage';
import { TeamPage } from '@/pages/team/TeamPage';
import { NotesPage } from '@/pages/NotesPage';
import { ProjectsPage } from '@/pages/ProjectsPage';
import { ProjectDetailPage } from '@/pages/ProjectDetailPage';
import { GraphPage } from '@/pages/GraphPage';
import { CodeGraphPage } from '@/pages/CodeGraphPage';
import { OverviewPage } from '@/pages/OverviewPage';
import { ActivityPage } from '@/pages/activity/ActivityPage';
import { HealthPage } from '@/pages/HealthPage';
import { UsagePage } from '@/pages/UsagePage';
import { SettingsPage } from '@/pages/SettingsPage';

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<AgentPage />} />
        <Route path="chat" element={<AgentPage />} />
        <Route path="chat/:sessionId" element={<AgentPage />} />
        <Route path="team" element={<TeamPage />} />
        <Route path="notes" element={<NotesPage />} />
        <Route path="sources" element={<ProjectsPage />} />
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
