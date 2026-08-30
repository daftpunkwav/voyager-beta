/** 资源库感知:列表页报当前流条数;详情页报类型 + 标题(标题未到就用 id),
 *  不把 README/正文塞进 summary。列表数据在 react-query,详情标题在组件数据里,
 *  都由页面写入下方 module cache(学 noteQuote.ts 先例),provider 只读。 */

import type { PageProbe } from '@/bridge/pageContext';

// ---- 列表页(/sources) ----

/** null = 资源流未就绪(加载中/失败),不谎报 0 项。 */
let listCount: number | null = null;

export function rememberSourcesListCount(count: number | null): void {
  listCount = count;
}

export function lastSourcesListCount(): number | null {
  return listCount;
}

export const sourcesProvider: PageProbe = {
  page: 'sources',
  report() {
    const n = listCount;
    if (n === null) return null;
    return { summary: `资源库 · ${n} 项`, counts: { items: n } };
  },
};

// ---- 详情页(/sources/repo|doc|web/:id) ----

export interface SourceDetail {
  /** repo / doc / web(无 kind 的旧路由按 repo 处理) */
  kind: string;
  id: string;
  /** 标题未到达时为空串,probe 落到 id */
  title: string;
}

let detail: SourceDetail | null = null;

export function rememberSourceDetail(next: SourceDetail | null): void {
  detail = next;
}

export function lastSourceDetail(): SourceDetail | null {
  return detail;
}

const KIND_LABELS: Record<string, string> = {
  repo: '仓库',
  doc: '文档',
  web: '网页',
};

export const sourceDetailProvider: PageProbe = {
  // 后端同属 sources 领域(报告的 page 字段仍是 sources)
  page: 'sources',
  report() {
    const d = detail;
    if (!d) return null;
    const kindLabel = KIND_LABELS[d.kind] ?? d.kind;
    const title = d.title.trim().slice(0, 40);
    return {
      summary: `资源详情 · ${kindLabel} · ${title || d.id}`,
      selected: d.id,
    };
  },
};
