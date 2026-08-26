import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import { useUIStore } from '@/stores/uiStore';
import { userInitials } from '@/utils/user';

const PAGE_LABEL: Record<string, string> = {
  '/': '对话',
  '/team': '团队',
  '/notes': '笔记',
  '/sources': '资源库',
  '/graph': '图谱',
  '/overview': '总览',
  '/activity': '活动',
  '/system/health': '服务状态',
  '/usage': '用量',
  '/settings': '设置',
};

function resolveCrumbLabel(pathname: string): string {
  if (pathname.startsWith('/sources/') && pathname !== '/sources') return '资源详情';
  if (pathname.startsWith('/graph/') && pathname !== '/graph') return '代码图谱';
  if (pathname.startsWith('/chat/') && pathname !== '/') return '对话';
  if (pathname.startsWith('/code-graph/')) return '代码图谱';
  return PAGE_LABEL[pathname] ?? '总览';
}

function readSystemPrefersDark(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false;
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

export function Topbar() {
  const user = useAuthStore((s) => s.user);
  const theme = useUIStore((s) => s.theme);
  const setTheme = useUIStore((s) => s.setTheme);
  const navigate = useNavigate();
  const location = useLocation();
  const searchRef = useRef<HTMLInputElement>(null);
  const initials = userInitials(user?.username);

  const [systemDark, setSystemDark] = useState<boolean>(readSystemPrefersDark);
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const update = () => setSystemDark(mq.matches);
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, []);
  const isDark = theme === 'dark' || (theme === 'system' && systemDark);

  const onSearchKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      const q = searchRef.current?.value.trim() ?? '';
      navigate(q ? `/sources?q=${encodeURIComponent(q)}` : '/sources');
    }
  };

  const toggleTheme = () => {
    setTheme(isDark ? 'light' : 'dark');
  };

  return (
    <header className="topbar">
      <div className="topbar-crumb">
        <strong>{resolveCrumbLabel(location.pathname)}</strong>
      </div>
      <div className="topbar-spacer" />
      <div className="topbar-search">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={14} height={14}>
          <circle cx="11" cy="11" r="7" />
          <path d="M21 21l-4.3-4.3" />
        </svg>
        <input
          ref={searchRef}
          type="text"
          placeholder="全局搜索..."
          autoComplete="off"
          onKeyDown={onSearchKey}
        />
        <kbd>⌘K</kbd>
      </div>
      {user?.github_login && (
        <span className="gh-bound" title="GitHub 账号已绑定">
          <svg viewBox="0 0 24 24" fill="currentColor" width={14} height={14}>
            <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.92.58.11.79-.25.79-.56v-2c-3.2.7-3.87-1.36-3.87-1.36-.52-1.33-1.28-1.69-1.28-1.69-1.05-.72.08-.7.08-.7 1.16.08 1.78 1.19 1.78 1.19 1.04 1.78 2.72 1.27 3.38.97.1-.75.4-1.27.74-1.56-2.55-.29-5.24-1.28-5.24-5.7 0-1.26.45-2.29 1.18-3.1-.12-.29-.51-1.46.11-3.04 0 0 .97-.31 3.18 1.18.92-.26 1.91-.39 2.89-.39.98 0 1.97.13 2.89.39 2.21-1.49 3.18-1.18 3.18-1.18.62 1.58.23 2.75.11 3.04.74.81 1.18 1.84 1.18 3.1 0 4.43-2.7 5.41-5.26 5.69.41.36.78 1.06.78 2.13v3.16c0 .31.21.68.8.56C20.21 21.38 23.5 17.08 23.5 12 23.5 5.65 18.35.5 12 .5z" />
          </svg>
          @{user.github_login}
        </span>
      )}
      <button type="button" className="topbar-action" title="主题切换" onClick={toggleTheme}>
        {isDark ? (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={16} height={16}>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={16} height={16}>
            <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
          </svg>
        )}
      </button>
      <button type="button" className="topbar-action" title="通知" style={{ position: 'relative' }}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={16} height={16}>
          <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.7 21a2 2 0 0 1-3.4 0" />
        </svg>
        <span className="dot" />
      </button>
      <button type="button" className="topbar-action" title="帮助">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={16} height={16}>
          <circle cx="12" cy="12" r="9" />
          <path d="M9.5 9a2.5 2.5 0 0 1 5 0c0 1.5-2.5 2-2.5 3.5" />
          <circle cx="12" cy="17" r="0.8" fill="currentColor" />
        </svg>
      </button>
      <button
        type="button"
        className="topbar-action"
        title="个人"
        style={{ display: 'grid', placeItems: 'center' }}
        onClick={() => navigate('/team')}
      >
        <div className="avatar" style={{ width: 28, height: 28, fontSize: 11 }}>
          {initials}
        </div>
      </button>
    </header>
  );
}
