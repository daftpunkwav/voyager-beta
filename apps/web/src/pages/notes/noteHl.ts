/** 笔记底纹色板与标记语法:==tone:text==,不含扫描/写入算法。 */

export const NOTE_HL_TONES = ['warm', 'cool', 'rose', 'lime', 'violet', 'sand'] as const;
export type NoteHlTone = (typeof NOTE_HL_TONES)[number] | `rgb${string}`;
export type NoteHlAction = NoteHlTone | 'clear';

export const NOTE_HL_LABEL: Record<(typeof NOTE_HL_TONES)[number], string> = {
  warm: '暖黄底纹',
  cool: '冷蓝底纹',
  rose: '玫红底纹',
  lime: '青绿底纹',
  violet: '青紫底纹',
  sand: '沙橙底纹',
};

/** 标记名:常驻色或 rgb + 6 位十六进制(小写)。 */
export const NOTE_HL_KIND = 'warm|cool|rose|lime|violet|sand|rgb[0-9a-fA-F]{6}';
export const NOTES_HL_RGB_KEY = 'notes-hl-rgb';
export const NOTES_HL_RGB_DEFAULT = '7c3aed';

const RGB_TONE = /^rgb[0-9a-f]{6}$/;
const HEX6 = /^[0-9a-f]{6}$/;
const TONE_AT = new RegExp(`^(${NOTE_HL_KIND}):`, 'i');

export function isRgbTone(tone: string): boolean {
  return RGB_TONE.test(tone);
}

/** 接受 warm / rgb7c3aed / #7c3aed / 7c3aed,非法则 null。 */
export function parseHlTone(raw: string): NoteHlTone | null {
  const t = raw.trim().toLowerCase();
  if ((NOTE_HL_TONES as readonly string[]).includes(t)) return t as (typeof NOTE_HL_TONES)[number];
  if (RGB_TONE.test(t)) return t as NoteHlTone;
  const hex = t.startsWith('#') ? t.slice(1) : t;
  if (HEX6.test(hex)) return `rgb${hex}` as NoteHlTone;
  return null;
}

export function rgbToneHex(tone: string): string | null {
  if (!isRgbTone(tone)) return null;
  return `#${tone.slice(3)}`;
}

export function readToneAt(text: string, innerFrom: number): { tone: NoteHlTone; innerStart: number } | null {
  const m = TONE_AT.exec(text.slice(innerFrom));
  if (!m || m.index !== 0) return null;
  return { tone: m[1].toLowerCase() as NoteHlTone, innerStart: innerFrom + m[0].length };
}

export function parseNoteHighlight(text: string): { tone: NoteHlTone; inner: string } | null {
  if (!text) return null;
  if (!(text.startsWith('==') && text.endsWith('==') && text.length >= 4)) return null;
  const body = text.slice(2, -2);
  if (body.includes('==')) return null;
  const m = TONE_AT.exec(body);
  if (m && m.index === 0) {
    return { tone: m[1].toLowerCase() as NoteHlTone, inner: body.slice(m[0].length) };
  }
  return { tone: 'warm', inner: body };
}

export function wrapNoteHighlight(inner: string, tone: NoteHlTone): string {
  return `==${tone}:${inner}==`;
}

/** 预览 sanitizer 只放行已识别的 notes-hl-* class;自定义色带 --notes-hl。 */
export function notesHlMarkProps(raw: unknown): { className: string; color?: string } {
  const text = Array.isArray(raw) ? raw.join(' ') : String(raw ?? '');
  const named = new RegExp(`\\bnotes-hl-(${NOTE_HL_TONES.join('|')})\\b`).exec(text);
  if (named) return { className: `notes-hl-${named[1]}` };
  const rgb = /\bnotes-hl-(rgb[0-9a-f]{6})\b/i.exec(text);
  if (rgb) {
    const token = rgb[1].toLowerCase();
    return { className: `notes-hl-rgb notes-hl-${token}`, color: `#${token.slice(3)}` };
  }
  return { className: 'notes-hl-warm' };
}

/** 代码围栏里误写入的 ==tone:…==:仅用于 ASCII 架构图识别,不改源码。 */
export function recoverTonedMarkup(text: string): string {
  const closed = new RegExp(`==(${NOTE_HL_KIND}):((?:(?!==).)+)==`, 'gi');
  const open = new RegExp(`==(${NOTE_HL_KIND}):`, 'gi');
  let s = text;
  for (let n = 0; n < 16; n += 1) {
    const next = s.replace(closed, '$2');
    if (next === s) break;
    s = next;
  }
  s = s.replace(open, '');
  return s.replace(/(^|[^=])==(?!=)/gm, '$1');
}
