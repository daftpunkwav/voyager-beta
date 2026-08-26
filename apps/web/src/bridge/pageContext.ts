/** 页面感知协议(§5.1 / §9.20):每页一个 probe,实现 report() 输出"索引行+摘要"。
 * 摘要不暴露正文;数据未加载完时返回 null,PageProbe 跳过该次上报。
 *
 * 本文件定义协议本身,具体实现见各 page 的 provider.ts(页面自治)。 */

export interface PageProbe {
  /** 页面标识(上报到后端时用,作为 page 字段) */
  page: string;
  /** 上报当前页摘要(单行索引行,长度可控)+ 计数 + 当前选中(可空) */
  report(): { summary: string; counts?: Record<string, number>; selected?: string } | null;
}
