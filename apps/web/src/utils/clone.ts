/**
 * 深克隆：优先使用原生 structuredClone，失败时回退到 JSON 往返。
 * 注意：JSON 回退会丢失 Date / Map / Set / 函数 / Symbol 键，但当前 mock 数据仅含 plain object。
 */
export function deepClone<T>(value: T): T {
  if (typeof structuredClone === 'function') {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value)) as T;
}
