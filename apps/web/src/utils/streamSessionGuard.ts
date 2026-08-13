/** 流式回调是否仍应对当前 store 写入（会话未切换）。 */
export function isStreamSessionActive(
  originSessionId: string | null | undefined,
  currentSessionId: string | null | undefined,
): boolean {
  return Boolean(originSessionId) && originSessionId === currentSessionId;
}
