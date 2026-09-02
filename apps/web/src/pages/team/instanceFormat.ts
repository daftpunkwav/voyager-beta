/** 团队页实例 / checkpoint 条目的展示格式化(phase-70 从 InstanceList 抽出共用)。 */

/** started_ts 是秒级 unix 时间戳(agent/runtime/state.py time.time()) */
export function relativeTime(ts: number): string {
  if (!ts) return '';
  const diff = Math.max(0, Date.now() / 1000 - ts);
  if (diff < 60) return '刚刚';
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  return `${Math.floor(diff / 86400)} 天前`;
}

/** 实例状态 → 状态色片(shell.css .inst--*) */
export function statusChipClass(status: string): string {
  switch (status) {
    case 'running':
      return 'inst--running';
    case 'completed':
      return 'inst--done';
    case 'failed':
      return 'inst--failed';
    case 'paused':
      return 'inst--paused';
    default:
      return 'inst--muted';
  }
}
