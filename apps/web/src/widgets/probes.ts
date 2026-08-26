/** 页面感知协议(§5.1 / §9.20):每页一个 probe,实现 report() 输出**索引级**摘要。
 * 摘要不塞正文;数据未加载完时返回 null,PageProbe 跳过该次上报。
 *
 * 本文件只依赖各页面的 provider 摘要出口，不直接读取页面私有 store(§10.1)。
 */

import type { PageProbe } from '@/bridge/pageContext';
import { activityProvider } from '@/pages/activity/provider';
import { graphProvider } from '@/pages/graph/provider';
import { notesProvider } from '@/pages/notes/provider';
import { sourcesProvider } from '@/pages/sources/provider';
import { teamProvider } from '@/pages/team/provider';
import { usageProvider } from '@/pages/usage/provider';

export type { PageProbe } from '@/bridge/pageContext';

/** 路由 -> probe 注册表;各页在此注册(页面自治,新增页面 = 加一条)。 */
export const PAGE_PROBES: Record<string, PageProbe> = {
  '/notes': notesProvider,
  '/sources': sourcesProvider,
  '/graph': graphProvider,
  '/activity': activityProvider,
  '/team': teamProvider,
  '/usage': usageProvider,
};
