/** Voyager 应用壳:液态玻璃导航(Sidebar + Topbar)
 * + 路由感知 activePage(给 Sidebar 用)
 * + 常驻 ServiceBadges 条 + PageProbe + FloatingChat(chat 路由时 FloatingChat 隐藏)。
 *
 * 关键修复(vs. 之前版本):移除给 .app 加 .agent-shell 的逻辑。
 * 旧实现让 .app 被 4 列 grid 覆盖,主列只剩 280px,导致 Topbar 压缩到 280px
 * 且滚出视口(y=-805)。现在 .app 永远保持 2 列布局(Sidebar + main),
 * AgentPage 内部用 .chat-layout 自管理 3 栏布局。 */

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
 * + 服务状态条 + PageProbe + FloatingChat。 */
export function AppShell() {
  const { pathname } = useLocation();
  const activePage = resolveActivePage(pathname);
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed);
  const onChat = pathname === '/' || pathname.startsWith('/chat');

  return (
    <div
      className={[
        'app',
        sidebarCollapsed ? 'sidebar-collapsed' : '',
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
