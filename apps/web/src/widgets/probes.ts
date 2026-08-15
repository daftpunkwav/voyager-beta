/** 页面感知协议(§5.1):每页一个 probe,实现 report() 输出**索引级**摘要。
 * 摘要不塞正文(§9.20);数据未加载完时返回 null,PageProbe 跳过该次上报。
 */

import { useGraphStore } from '@/pages/graph/graphStore';
import { useNotesStore } from '@/pages/notes/notesStore';
import { useSourcesStore } from '@/pages/sources/sourcesStore';
import { useActivityStore } from '@/pages/activity/activityStore';
import { useTeamStore } from '@/pages/team/teamStore';
import { useUsageStore } from '@/pages/usage/usageStore';

export interface PageProbe {
  page: string;
  report(): { summary: string; counts?: Record<string, number>; selected?: string } | null;
}

/** 路由 -> probe 注册表;各页在此注册(页面自治,新增页面 = 加一条)。 */
export const PAGE_PROBES: Record<string, PageProbe> = {
  '/notes': {
    page: 'notes',
    report() {
      const { summaries, current, loading } = useNotesStore.getState();
      if (loading && summaries.length === 0) return null;
      return {
        summary: current
          ? `${summaries.length} 篇笔记,当前打开《${current.title}》`
          : `${summaries.length} 篇笔记`,
        counts: { notes: summaries.length },
        selected: current?.title ?? '',
      };
    },
  },
  '/sources': {
    page: 'sources',
    report() {
      const { repos, loading } = useSourcesStore.getState();
      if (loading && repos.length === 0) return null;
      const ready = repos.filter((r) => r.status === 'ready').length;
      return {
        summary: `${repos.length} 个仓库(${ready} 就绪)`,
        counts: { repos: repos.length, ready },
      };
    },
  },
  '/graph': {
    page: 'graph',
    report() {
      const { project, nodes, edges, selected, stats, loading } = useGraphStore.getState();
      if (loading && nodes.size === 0) return null;
      const sel = selected ? nodes.get(selected)?.name ?? '' : '';
      const total = stats?.total_nodes ?? nodes.size;
      return {
        summary: `项目 ${project || '(未选)'}:${total} 节点 / ${stats?.total_edges ?? edges.size} 边`,
        counts: { loaded: nodes.size },
        selected: sel,
      };
    },
  },
  '/activity': {
    page: 'activity',
    report() {
      const { events, group } = useActivityStore.getState();
      return { summary: `活动流 ${events.length} 条,筛选 ${group}`, counts: { events: events.length } };
    },
  },
  '/team': {
    page: 'team',
    report() {
      const { running } = useTeamStore.getState();
      return {
        summary: `团队页:${running.length} 个实例运行中`,
        counts: { running: running.length },
      };
    },
  },
  '/usage': {
    page: 'usage',
    report() {
      const { stats } = useUsageStore.getState();
      if (!stats) return null;
      return {
        summary: `用量近 ${stats.days} 天:${stats.calls} 次调用`,
        counts: { calls: stats.calls },
      };
    },
  },
};
