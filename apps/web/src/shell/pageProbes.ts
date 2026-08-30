/** 页面感知注册表(§5.1 / §9.20):路由 -> 该页公开 provider 摘要出口。
 * 每页在自己的 pages/<域>/provider.ts 实现 PageProbe 协议(report() 输出“索引行+摘要”,
 * 不暴露正文;数据未就绪返回 null,PageProbe 跳过该次上报)。
 * 放在 shell 层:shell 负责编排页面,依赖方向 shell → pages 合法;
 * widgets/PageProbe 组件只消费本表,不得反向 import 页面。 */

import type { PageProbe } from '@/bridge/pageContext';
import { activityProvider } from '@/pages/activity/provider';
import { chatProvider } from '@/pages/chat/provider';
import { graphProvider } from '@/pages/graph/provider';
import { codeGraphProvider } from '@/pages/code-graph/provider';
import { notesProvider } from '@/pages/notes/provider';
import { sourcesProvider, sourceDetailProvider } from '@/pages/sources/provider';
import { teamProvider } from '@/pages/team/provider';

export type { PageProbe } from '@/bridge/pageContext';

/** page 名 -> probe(各页在此注册;页面自治,新增页面 = 加一条)。
 *  code-graph 是图谱页的详情视图、source-detail 是资源详情页,
 *  probe.page 仍分别报 graph / sources(后端同一领域)。 */
export const PAGE_PROBES: Record<string, PageProbe> = {
  chat: chatProvider,
  notes: notesProvider,
  sources: sourcesProvider,
  'source-detail': sourceDetailProvider,
  graph: graphProvider,
  'code-graph': codeGraphProvider,
  team: teamProvider,
  activity: activityProvider,
};

/** 路由 -> page 名(前缀解析,与 pageMeta.resolvePageTitle 同口径;不再全等字典)。
 *  settings / usage / health / overview 不返回:设置含密钥,总览周报是占位死链。 */
export function resolvePageName(pathname: string): string | null {
  if (pathname === '/' || pathname === '/chat' || pathname.startsWith('/chat/')) return 'chat';
  if (pathname === '/notes' || pathname.startsWith('/notes/')) return 'notes';
  if (pathname === '/sources') return 'sources';
  if (pathname.startsWith('/sources/')) return 'source-detail';
  if (pathname === '/graph' || pathname.startsWith('/graph/')) return 'graph';
  if (pathname === '/code-graph' || pathname.startsWith('/code-graph/')) return 'code-graph';
  if (pathname === '/team') return 'team';
  if (pathname === '/activity') return 'activity';
  return null;
}

/** 路由 -> 该页 probe;未注册页返回 null(不上报)。 */
export function resolvePageProbe(pathname: string): PageProbe | null {
  const page = resolvePageName(pathname);
  if (!page) return null;
  return PAGE_PROBES[page] ?? null;
}
