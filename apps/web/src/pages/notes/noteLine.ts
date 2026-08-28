/** 笔记正文行级操作:草稿 id、行前缀切换、分栏滚动比例。 */

/** 新建草稿 id 为 'new';其余(UUID / mock n_*)均视为已有笔记 */
export function isPersistedNoteId(id: string | null | undefined): id is string {
  return Boolean(id && id !== 'new');
}

/**
 * 行前缀切换:已是该前缀则去掉,否则换掉旧的标题/引用/列表前缀再套上新前缀。
 * `- ` 不误吞任务列表 `- [ ] `。
 */
export function applyLinePrefix(text: string, prefix: string): string {
  const isTask = /^[-*]\s\[[ x]\]\s/.test(text);
  if (text.startsWith(prefix) && !(prefix === '- ' && isTask)) {
    return text.slice(prefix.length);
  }
  const stripped = text.replace(/^(#{1,6}\s|>\s?|[-*]\s(?:\[[ x]\]\s)?|\d+\.\s)/, '');
  return prefix + stripped;
}

/** 按滚动比例把 from 同步到 to;可滚动距离为 0 时跳过。 */
export function syncScrollRatio(from: HTMLElement, to: HTMLElement): void {
  const fromMax = from.scrollHeight - from.clientHeight;
  const toMax = to.scrollHeight - to.clientHeight;
  if (fromMax <= 0 || toMax <= 0) return;
  to.scrollTop = (from.scrollTop / fromMax) * toMax;
}
