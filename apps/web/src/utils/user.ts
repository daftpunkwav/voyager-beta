/**
 * 取用户名前两位字符作为头像字母。
 * - 缺失用户名返回 'G' (guest)
 * - 大写化，便于 UI 直接展示
 */
export function userInitials(username?: string | null): string {
  if (!username) return 'G';
  return username.slice(0, 2).toUpperCase();
}