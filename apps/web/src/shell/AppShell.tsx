/** 应用壳:左侧分组导航(仅渲染已开放页面)+ 服务徽章条 + <Outlet/>。 */

import { NavLink, Outlet } from 'react-router-dom';
import { ServiceBadges } from './ServiceBadge';

/** 导航分组:阶段推进中逐组点亮;组内无可渲染项时整组不出现(未做的不上导航)。 */
const NAV_GROUPS: { label: string; items: { to: string; label: string }[] }[] = [
  {
    label: '系统',
    items: [{ to: '/system/health', label: '服务状态' }],
  },
];

export function AppShell() {
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
    </div>
  );
}
