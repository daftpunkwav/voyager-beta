/** URL 闸门:内部跳转只允许同源相对路径;外链只允许 http(s)。 */

const INTERNAL = /^\/[A-Za-z0-9\-._~:/?#[\]@!$&'()*+,;=%]*$/;

/** 路径段为 `..`(含百分号编码)则视为穿越。`foo..bar` 这种文件名放行。 */
function hasDotDotSegment(raw: string): boolean {
  let decoded = raw;
  try {
    decoded = decodeURIComponent(raw);
  } catch {
    return true;
  }
  const norm = decoded.replace(/\\/g, '/');
  return /(^|\/)\.\.(\/|$)/.test(norm);
}

/** 供 react-router navigate 的站内路径。拒绝协议相对、反斜杠、javascript: 等。 */
export function safeInternalPath(raw: unknown): string | null {
  if (typeof raw !== 'string') return null;
  const path = raw.trim();
  if (!path.startsWith('/') || path.startsWith('//')) return null;
  if (path.includes('\\') || path.includes('://')) return null;
  if (/[\u0000-\u001f\u007f]/.test(path)) return null;
  if (hasDotDotSegment(path)) return null;
  if (!INTERNAL.test(path)) return null;
  return path;
}

/** 外链 href;非法时返回 undefined,调用方应改渲染为文本。 */
export function safeHttpUrl(raw: unknown): string | undefined {
  if (typeof raw !== 'string' || !raw.trim()) return undefined;
  try {
    const url = new URL(raw.trim());
    if (url.protocol === 'http:' || url.protocol === 'https:') return url.href;
  } catch {
    return undefined;
  }
  return undefined;
}

/** Markdown 图源:站点相对路径 / attachment 协议 / http(s)。 */
export function safeImgSrc(raw: unknown): string | undefined {
  if (typeof raw !== 'string' || !raw) return undefined;
  if (raw.startsWith('attachment://')) {
    const id = raw.slice('attachment://'.length);
    if (!id || id.includes('..') || id.includes('/') || id.includes('\\')) return undefined;
    return `/api/notes/assets/${encodeURIComponent(id)}`;
  }
  if (raw.startsWith('/') && !raw.startsWith('//')) {
    if (raw.includes('\\') || hasDotDotSegment(raw)) return undefined;
    return raw;
  }
  return safeHttpUrl(raw);
}
