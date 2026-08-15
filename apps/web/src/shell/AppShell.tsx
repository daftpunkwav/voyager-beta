/** 应用壳:左侧分组导航(仅渲染已开放页面)+ 服务徽章条 + <Outlet/>
 * + 常驻悬浮窗与页面感知(chat 路由时悬浮窗隐藏,§10.12)。 */

import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { ServiceBadges } from './ServiceBadge';
import { FloatingChat } from '@/widgets/FloatingChat';
import { PageProbe } from '@/widgets/PageProbe';

/** 导航分组:阶段推进中逐组点亮;组内无可渲染项时整组不出现(未做的不上导航)。 */
const NAV_GROUPS: { label: string; items: { to: string; label: string }[] }[] = [
  {
    label: 'Agent',
    items: [
      { to: '/', label: '对话' },
      { to: '/team', label: '团队' },
    ],
  },
  {
    label: '领域',
    items: [
      { to: '/notes', label: '笔记' },
      { to: '/sources', label: '资源库' },
      { to: '/graph', label: '图谱' },
    ],
  },
  {
    label: '系统',
    items: [
      { to: '/overview', label: '总览' },
      { to: '/system/health', label: '服务状态' },
      { to: '/activity', label: '活动' },
      { to: '/usage', label: '用量' },
      { to: '/settings', label: '设置' },
    ],
  },
];

export function AppShell() {
  const location = useLocation();
  const onChat = location.pathname === '/';
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <span className="sidebar-logo" aria-hidden />
          <span className="sidebar-name">控制台</span>
        </div>
        {NAV_GROUPS.filter((g) => g.items.length > 0).map((group) => (
          <nav className="sidebar-section" key={group.label}>
            <div className="label">{group.label}</div>
            {group.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        ))}
        <div className="sidebar-footer">
          <div className="small muted">骨架阶段</div>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <ServiceBadges />
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
      <PageProbe />
      {onChat ? null : <FloatingChat />}
    </div>
  );
}
