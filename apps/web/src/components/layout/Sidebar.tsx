import { NavLink } from 'react-router-dom';
import { Link } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import { useProjectStats } from '@/hooks/useProjects';
import { useAllNotes } from '@/hooks/useNotes';
import { NavIcons } from '@/components/icons/NavIcons';
import { userInitials } from '@/utils/user';
import { useUIStore } from '@/stores/uiStore';

/** 与 archive/sidebar.js NAV_ITEMS 顺序一致 */
const NAV_ITEMS = [
  { key: 'overview', label: '总览', path: '/', badge: null as string | null },
  { key: 'projects', label: '项目库', path: '/projects', badge: 'count' as const },
  { key: 'agent', label: 'Agent Chat', path: '/agent', badge: 'AI' as const },
  { key: 'graph', label: '图谱', path: '/graph', badge: null },
  { key: 'usage', label: '用量', path: '/usage', badge: null },
  { key: 'notes', label: '笔记', path: '/notes', badge: 'notes' as const },
  { key: 'settings', label: '设置', path: '/settings', badge: null },
] as const;

export type SidebarPageKey = (typeof NAV_ITEMS)[number]['key'] | 'project-detail';

interface SidebarProps {
  /** 当前高亮页（项目详情页高亮「项目库」） */
  activePage?: SidebarPageKey;
}

export function Sidebar({ activePage }: SidebarProps) {
  const user = useAuthStore((s) => s.user);
  const { data: stats } = useProjectStats();
  const { data: notes } = useAllNotes();
  const initials = userInitials(user?.username);
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);

  return (
    <aside className={`sidebar${collapsed ? ' is-collapsed' : ''}`}>
      <div className="sidebar-brand">
        <div className="sidebar-logo" title="Voyager">
          RP
        </div>
        {!collapsed && (
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.2 }}>
            <span className="sidebar-name">Voyager</span>
            <span style={{ fontSize: 10, color: 'var(--text-400)', letterSpacing: '0.06em' }}>
              v1.0.0
            </span>
          </div>
        )}
        <button
          type="button"
          className="sidebar-collapse-btn"
          title={collapsed ? '展开导航' : '折叠导航'}
          aria-label={collapsed ? '展开导航' : '折叠导航'}
          aria-expanded={!collapsed}
          onClick={toggleSidebar}
        >
          {collapsed ? '⟩' : '⟨'}
        </button>
      </div>

      {NAV_ITEMS.map((item) => {
        const Icon = NavIcons[item.key];
        const isProjectDetail = activePage === 'project-detail' && item.key === 'projects';
        return (
          <NavLink
            key={item.key}
            to={item.path}
            end={item.path === '/'}
            title={item.label}
            className={({ isActive }) => {
              const active = isActive || isProjectDetail;
              const classes = ['nav-item'];
              if (active) classes.push('active');
              if (item.badge === 'AI') classes.push('ai-badge');
              return classes.join(' ');
            }}
            data-nav-key={item.key}
          >
            <Icon />
            {!collapsed && <span>{item.label}</span>}
            {!collapsed && item.badge === 'AI' && <span className="nav-badge">AI</span>}
            {!collapsed && item.badge === 'count' && stats && (
              <span className="nav-badge">{stats.total}</span>
            )}
            {!collapsed && item.badge === 'notes' && notes && (
              <span className="nav-badge">{notes.length}</span>
            )}
          </NavLink>
        );
      })}

      <div className="sidebar-footer">
        <Link
          className="nav-item"
          to="/settings"
          title={user?.username ?? '访客'}
          style={{ padding: '8px 10px' }}
        >
          <div className="avatar" style={{ width: 28, height: 28, fontSize: 11 }}>
            {initials}
          </div>
          {!collapsed && (
            <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.2, flex: 1, minWidth: 0 }}>
              <span style={{ fontSize: 12, fontWeight: 600 }}>{user?.username ?? '访客'}</span>
              <span style={{ fontSize: 10, color: 'var(--text-400)' }}>
                Pro · {stats?.total ?? 0} / ∞
              </span>
            </div>
          )}
        </Link>
      </div>
    </aside>
  );
}
