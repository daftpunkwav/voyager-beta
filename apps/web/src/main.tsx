import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from '@/App';
import { useTheme } from '@/shell/useTheme';
import { initActivityReport } from '@/bridge/activity';

// —— 全局样式(液态玻璃设计系统 + shell + 全局 + 各 page 私有) ——
import '@/styles/design-system.css';
import '@/styles/liquid-glass.css';
import '@/styles/shell.css';
import '@/styles/global.css';
import '@/styles/pages/index.css';

// react-query 客户端(保留 @tanstack/react-query 5.x 兼容旧 hook 形态;
// 未来若彻底替换,见 docs/audit/04-frontend-migration-detail.html §3)
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      gcTime: 30 * 60 * 1000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function Root() {
  useTheme();
  void initActivityReport();
  return (
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </StrictMode>
  );
}

const rootEl = document.getElementById('root');
if (!rootEl) {
  throw new Error('Root element #root not found');
}
createRoot(rootEl).render(<Root />);
