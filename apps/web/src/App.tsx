/** 路由表:骨架页 + 设置页已点亮,其余功能页随后续阶段逐个开放。 */

import { Route, Routes } from 'react-router-dom';
import { AppShell } from '@/shell/AppShell';
import { HealthPage } from '@/pages/HealthPage';
import { Placeholder } from '@/pages/Placeholder';
import { SettingsPage } from '@/pages/settings/SettingsPage';

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Placeholder />} />
        <Route path="system/health" element={<HealthPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}
