/** 当前栏目名:只出现在顶栏,与搜索框同高;页内不再重复写。 */

export function resolvePageTitle(pathname: string): string {
  if (pathname === '/' || pathname.startsWith('/chat')) return '对话';
  if (pathname === '/team') return '团队';
  if (pathname === '/notes' || pathname.startsWith('/notes')) return '笔记';
  if (pathname === '/sources' || pathname.startsWith('/sources')) return '资源库';
  if (
    pathname === '/graph' ||
    pathname.startsWith('/graph/') ||
    pathname.startsWith('/code-graph')
  ) {
    return '图谱';
  }
  if (pathname === '/overview') return '总览';
  if (pathname === '/activity') return '活动';
  if (pathname === '/system/health') return '服务状态';
  if (pathname === '/usage') return '用量';
  if (pathname === '/settings') return '设置';
  return '';
}
