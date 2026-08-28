/** 本机会话:环回 bootstrap 写入 Cookie,后续 API 带 credentials。 */

export async function ensureSession(): Promise<void> {
  try {
    await fetch('/api/session/bootstrap', { credentials: 'include' });
  } catch {
    // 后端未启动时不挡 UI;后续 callCapability 会报 NETWORK
  }
}
