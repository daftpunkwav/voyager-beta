/** Voyager 应用壳:RepoPilot 风格液态玻璃导航(Sidebar + Topbar)
 * + 路由感知 activePage + Agent Chat 路由附加 agent-shell 类
 * + 常驻 ServiceBadges 条 + PageProbe + FloatingChat(chat 路由时 FloatingChat 隐藏)。 */

import { Outlet, useLocation } from 'react-router-dom';
import { Sidebar, type SidebarPageKey } from '@/components/layout/Sidebar';
import { Topbar } from '@/components/layout/Topbar';
import { ToastContainer } from '@/components/common/ToastContainer';
import { PageProbe } from '@/widgets/PageProbe';
import { FloatingChat } from '@/widgets/FloatingChat';
import { ServiceBadges } from './ServiceBadge';
import { useUIStore } from '@/stores/uiStore';

function resolveActivePage(pathname: string): SidebarPageKey {
  if (pathname === '/' || pathname.startsWith('/chat')) return 'chat';
  if (pathname === '/team') return 'team';
  if (pathname === '/notes') return 'notes';
  if (pathname === '/sources') return 'sources';
  if (pathname.startsWith('/sources/')) return 'source-detail';
  if (pathname === '/graph' || pathname.startsWith('/code-graph')) return 'graph';
  if (pathname === '/overview') return 'overview';
  if (pathname === '/activity') return 'activity';
  if (pathname === '/system/health') return 'health';
  if (pathname === '/usage') return 'usage';
  if (pathname === '/settings') return 'settings';
  return 'overview';
}

/** 标准应用壳:Sidebar + Topbar(搜索/主题/通知/avatar) + <Outlet/>
 * + 服务状态条(右下角)+ Agent 路由挂 .agent-shell 类让 AgentPage 切换 grid。 */
export function AppShell() {
  const { pathname } = useLocation();
  const activePage = resolveActivePage(pathname);
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed);
  const onChat = pathname === '/' || pathname.startsWith('/chat');
  const isAgentRoute = onChat;

  return (
    <div
      className={[
        'app',
        sidebarCollapsed ? 'sidebar-collapsed' : '',
        isAgentRoute ? 'agent-shell' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <Sidebar activePage={activePage} />
      <div className="main">
        <Topbar />
        <div className="svc-strip">
          <ServiceBadges />
        </div>
        <main className="content">
          <Outlet />
        </main>
      </div>
      <ToastContainer />
      <PageProbe />
      {onChat ? null : <FloatingChat />}
    </div>
  );
}
