/** 路由表:Agent Chat 为主页;系统/笔记/资源库/图谱/用量已点亮,其余随后续阶段开放。 */

import { Route, Routes } from 'react-router-dom';
import { AppShell } from '@/shell/AppShell';
import { ChatPage } from '@/pages/chat/ChatPage';
import { HealthPage } from '@/pages/HealthPage';
import { SettingsPage } from '@/pages/settings/SettingsPage';
import { NotesPage } from '@/pages/notes/NotesPage';
import { SourcesPage } from '@/pages/sources/SourcesPage';
import { GraphPage } from '@/pages/graph/GraphPage';
import { UsagePage } from '@/pages/usage/UsagePage';

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
      </Route>
    </Routes>
  );
}
