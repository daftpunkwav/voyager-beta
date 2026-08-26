import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from '@/App';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
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

/** 顶层降级 UI:全应用崩溃时显示,避免白屏;用户可刷新或回首页。
 * 签名匹配 ErrorBoundary.fallback: (error, reset) => ReactNode */
function RootErrorFallback(_error: Error, reset: () => void) {
  return (
    <div
      role="alert"
      style={{
        padding: 32,
        fontFamily: 'system-ui, sans-serif',
        color: '#3a3a3c',
      }}
    >
      <h2 style={{ marginTop: 0 }}>应用出现未捕获错误</h2>
      <p>请刷新页面或点击下方按钮重试。详细信息请查看浏览器控制台。</p>
      <button
        type="button"
        onClick={reset}
        style={{
          padding: '8px 16px',
          borderRadius: 8,
          border: '1px solid #c7c7cc',
          background: '#fff',
          cursor: 'pointer',
        }}
      >
        重试
      </button>
    </div>
  );
}

function Root() {
  useTheme();
  void initActivityReport();
  return (
    <StrictMode>
      <ErrorBoundary fallback={RootErrorFallback}>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      </ErrorBoundary>
    </StrictMode>
  );
}

const rootEl = document.getElementById('root');
if (!rootEl) {
  throw new Error('Root element #root not found');
}
createRoot(rootEl).render(<Root />);
