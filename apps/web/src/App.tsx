/** 路由表:本阶段只有 / 占位与 /system/health 调试页,后续阶段逐个点亮。 */

import { Route, Routes } from 'react-router-dom';
import { AppShell } from '@/shell/AppShell';
import { HealthPage } from '@/pages/HealthPage';
import { Placeholder } from '@/pages/Placeholder';

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Placeholder />} />
        <Route path="system/health" element={<HealthPage />} />
      </Route>
    </Routes>
  );
}
