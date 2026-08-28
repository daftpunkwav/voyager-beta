import { Link, NavLink } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import { NavIcons } from '@/components/icons/NavIcons';
import { userInitials } from '@/utils/user';
import { useUIStore } from '@/stores/uiStore';
import { PRODUCT_NAME } from '@/brand';
import { routes } from '@/utils/routes';

/** 导航分组:Agent / 领域 / 系统(随阶段点亮,未开放的不上导航)。 */
const NAV_ITEMS = [
  // —— Agent 主线 ——
  { key: 'chat', label: '对话', path: routes.chat, badge: 'AI' as const, group: 'agent' },
  { key: 'team', label: '团队', path: routes.team, badge: null, group: 'agent' },
  // —— 领域 ——
  { key: 'notes', label: '笔记', path: routes.notes, badge: null, group: 'domain' },
  { key: 'sources', label: '资源库', path: routes.sources, badge: null, group: 'domain' },
  { key: 'graph', label: '图谱', path: routes.graph, badge: null, group: 'domain' },
  // —— 系统 ——
  { key: 'overview', label: '总览', path: routes.overview, badge: null, group: 'system' },
  { key: 'health', label: '服务状态', path: routes.health, badge: null, group: 'system' },
  { key: 'activity', label: '活动', path: routes.activity, badge: null, group: 'system' },
  { key: 'usage', label: '用量', path: routes.usage, badge: null, group: 'system' },
  { key: 'settings', label: '设置', path: routes.settings, badge: null, group: 'system' },
] as const;

export type SidebarPageKey =
  | (typeof NAV_ITEMS)[number]['key']
  | 'source-detail'
  | 'session-detail';

interface SidebarProps {
  /** 当前高亮页(项目详情 / 聊天详情回退到所属主项) */
  activePage?: SidebarPageKey;
}

export function Sidebar({ activePage }: SidebarProps) {
  const user = useAuthStore((s) => s.user);
  const initials = userInitials(user?.username);
  const collapsed = useUIStore((s) => s.sidebarCollapsed);

  // 按 group 分组渲染
  const groups: Array<{ label: string; keys: string[] }> = [
    { label: 'Agent', keys: ['chat', 'team'] },
    { label: '领域', keys: ['notes', 'sources', 'graph'] },
    { label: '系统', keys: ['overview', 'health', 'activity', 'usage', 'settings'] },
  ];

  return (
    <aside className={`sidebar${collapsed ? ' is-collapsed' : ''}`}>
      <div className="sidebar-brand">
        <div className="sidebar-logo" title={PRODUCT_NAME}>{PRODUCT_NAME.slice(0, 1)}</div>
        {!collapsed && (
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.2 }}>
            <span className="sidebar-name">{PRODUCT_NAME}</span>
            <span className="sidebar-version">v1.0.0</span>
          </div>
        )}
      </div>

      {groups.map((g) => {
        const items = NAV_ITEMS.filter((it) => g.keys.includes(it.key));
        if (items.length === 0) return null;
        return (
          <nav className="sidebar-section" key={g.label}>
            {!collapsed && <div className="label">{g.label}</div>}
            {items.map((item) => {
              const Icon = (NavIcons as Record<string, (p: unknown) => React.ReactElement>)[item.key];
              const isFallback =
                (activePage === 'source-detail' && item.key === 'sources') ||
                (activePage === 'session-detail' && item.key === 'chat');
              return (
                <NavLink
                  key={item.key}
                  to={item.path}
                  end={item.path === '/'}
                  title={item.label}
                  className={({ isActive }) => {
                    const active = isActive || isFallback;
                    const classes = ['nav-item'];
                    if (active) classes.push('active');
                    if (item.badge === 'AI') classes.push('ai-badge');
                    return classes.join(' ');
                  }}
                  data-nav-key={item.key}
                >
                  {Icon ? <Icon /> : null}
                  {!collapsed && <span>{item.label}</span>}
                  {!collapsed && item.badge === 'AI' && <span className="nav-badge">AI</span>}
                </NavLink>
              );
            })}
          </nav>
        );
      })}

      <div className="sidebar-footer">
        <Link className="sidebar-user" to={routes.team} title={user?.username ?? '访客'}>
          <div className="avatar" aria-hidden>
            {initials}
          </div>
          {!collapsed && (
            <div className="sidebar-user__meta">
              <span className="sidebar-user__name">{user?.username ?? '访客'}</span>
              <span className="sidebar-user__hint">本机工作台</span>
            </div>
          )}
        </Link>
      </div>
    </aside>
  );
}
