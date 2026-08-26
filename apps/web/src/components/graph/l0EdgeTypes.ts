/**
 * L0 关系边类型与图例色（对齐原生引擎 分色细线）
 */
export const L0_EDGE_TYPES = [
  { id: 'similarity', label: '相似', color: '#2dd4bf' },
  { id: 'depends_on', label: '依赖', color: '#fb923c' },
  { id: 'recommend_learn', label: '推荐学习', color: '#f472b6' },
  { id: 'cross_http', label: '跨服务 HTTP', color: '#a78bfa' },
  { id: 'cross_async', label: '异步调用', color: '#fbbf24' },
] as const;

export type L0EdgeTypeId = (typeof L0_EDGE_TYPES)[number]['id'];

export const L0_EDGE_COLOR_MAP: Record<string, string> = Object.fromEntries(
  L0_EDGE_TYPES.map((t) => [t.id, t.color]),
);

export function labelForEdgeType(id: string | null | undefined): string {
  if (!id) return '全部';
  return L0_EDGE_TYPES.find((t) => t.id === id)?.label ?? id;
}

export function classifyErrorKind(kind: string | null | undefined, error?: string | null): string {
  if (kind === 'network') return '网络问题';
  if (kind === 'service') return '服务问题';
  if (kind === 'cancelled') return '已取消';
  if (error && /取消/.test(error)) return '已取消';
  if (error && /(timeout|network|连接|超时|dns|getaddrinfo)/i.test(error)) return '网络问题';
  if (
    error &&
    /(engine|502|503|服务|引擎|already exists|not an empty directory|命令失败|permission|disk|quota)/i.test(
      error,
    )
  ) {
    return '服务问题';
  }
  return '未知原因';
}
