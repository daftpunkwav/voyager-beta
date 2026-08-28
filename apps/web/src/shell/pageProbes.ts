/** 页面感知注册表(§5.1 / §9.20):路由 -> 该页公开 provider 摘要出口。
 * 每页在自己的 pages/<域>/provider.ts 实现 PageProbe 协议(report() 输出“索引行+摘要”,
 * 不暴露正文;数据未就绪返回 null,PageProbe 跳过该次上报)。
 * 放在 shell 层:shell 负责编排页面,依赖方向 shell → pages 合法;
 * widgets/PageProbe 组件只消费本表,不得反向 import 页面。 */

import type { PageProbe } from '@/bridge/pageContext';
import { activityProvider } from '@/pages/activity/provider';
import { notesProvider } from '@/pages/notes/provider';
import { teamProvider } from '@/pages/team/provider';

export type { PageProbe } from '@/bridge/pageContext';

/** 路由 -> probe 注册表(各页在此注册;页面自治,新增页面 = 加一条)。 */
export const PAGE_PROBES: Record<string, PageProbe> = {
  '/activity': activityProvider,
  '/notes': notesProvider,
  '/team': teamProvider,
};
