/** 前端品牌层:值由 Vite 从仓库根 brand.json 注入(§13.3 单一来源)。 */

export const PRODUCT_NAME: string = __BRAND__.productName;
export const PRODUCT_TAGLINE: string = __BRAND__.productTagline;
export const STORAGE = __BRAND__.storage;

/** 旧 key 迁到中性 key;已有新值则丢掉旧值。 */
export function migrateKey(current: string, legacy: string): void {
  try {
    if (typeof localStorage === 'undefined') return;
    if (localStorage.getItem(current) != null) {
      localStorage.removeItem(legacy);
      return;
    }
    const old = localStorage.getItem(legacy);
    if (old != null) {
      localStorage.setItem(current, old);
      localStorage.removeItem(legacy);
    }
  } catch {
    /* 隐私模式 */
  }
}

export function readKey(current: string, legacy: string): string | null {
  try {
    return localStorage.getItem(current) ?? localStorage.getItem(legacy);
  } catch {
    return null;
  }
}

export function writeKey(current: string, value: string): void {
  try {
    localStorage.setItem(current, value);
  } catch {
    /* noop */
  }
}
