/** 路由表:Agent Chat 为主页;系统/笔记/资源库/图谱/用量/活动/团队/总览已点亮,其余随后续阶段开放。 */

import { Route, Routes } from 'react-router-dom';
import { AppShell } from '@/shell/AppShell';
import { ChatPage } from '@/pages/chat/ChatPage';
import { HealthPage } from '@/pages/HealthPage';
import { SettingsPage } from '@/pages/settings/SettingsPage';
import { NotesPage } from '@/pages/notes/NotesPage';
import { SourcesPage } from '@/pages/sources/SourcesPage';
import { GraphPage } from '@/pages/graph/GraphPage';
import { UsagePage } from '@/pages/usage/UsagePage';
import { ActivityPage } from '@/pages/activity/ActivityPage';
import { TeamPage } from '@/pages/team/TeamPage';
import { OverviewPage } from '@/pages/overview/OverviewPage';

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<ChatPage />} />
        <Route path="system/health" element={<HealthPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="notes" element={<NotesPage />} />
        <Route path="sources" element={<SourcesPage />} />
        <Route path="graph" element={<GraphPage />} />
        <Route path="usage" element={<UsagePage />} />
        <Route path="activity" element={<ActivityPage />} />
        <Route path="team" element={<TeamPage />} />
        <Route path="overview" element={<OverviewPage />} />
      </Route>
    </Routes>
  );
}
