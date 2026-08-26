/** 页面感知摘要契约(§9.20 / §10.12)。
 *
 * 每个页面模块导出一个 PageProbe 实现，由 widgets/PageProbe 聚合上报。
 * 摘要只含索引级信息(数量/标题/选中项)，不含正文全文。
 */

export interface PageProbe {
  page: string;
  report(): { summary: string; counts?: Record<string, number>; selected?: string } | null;
}
