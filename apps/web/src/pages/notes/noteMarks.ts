/** 笔记底纹:Markdown 标记 ==tone:text==,不是富文本。用户工具栏与 agent mark_note_span 同语法。
 *
 * 写入:选区先拆已有标记再按行着色;围栏/行内代码/未闭合围栏内不改;
 * ASCII 框线与表格行整行不包,避免架构图与管道表被写入 ==。
 * 预览:在段落 phrasing 上跨节点包 <mark>,加粗/链接可落在底纹内,不再把 == 漏到画面上。
 */

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

const FENCE_OPEN = /^( {0,3})(`{3,}|~{3,})(.*)$/;
const BLOCK_PREFIX =
  /^(#{1,6}[ \t]+|(?:>[ \t]*)+|\s*[-*+][ \t]+\[[ xX]\][ \t]+|\s*[-*+][ \t]+|\s*\d+[.)][ \t]+)/;
const OBJECT_CHAR = '\uFFFC';

interface MdNode {
  type: string;
  value?: string;
  children?: MdNode[];
  data?: { hName?: string; hProperties?: Record<string, unknown> };
}

export interface NoteMarkSpan {
  start: number;
  innerStart: number;
  innerEnd: number;
  end: number;
  tone: NoteHlTone;
}

interface TextSpan {
  kind: 'text' | 'fence';
  start: number;
  end: number;
  tone: NoteHlTone | null;
}

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

function readToneAt(text: string, innerFrom: number): { tone: NoteHlTone; innerStart: number } | null {
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

export function splitBlockPrefix(line: string): { prefix: string; rest: string } {
  if (parseFenceLine(line)) return { prefix: line, rest: '' };
  const m = BLOCK_PREFIX.exec(line);
  if (!m) return { prefix: '', rest: line };
  return { prefix: m[0], rest: line.slice(m[0].length) };
}

function flattenTonedMarkup(text: string): string {
  let s = text;
  for (let n = 0; n < 32; n += 1) {
    const marks = scanMarks(s, true);
    if (marks.length === 0) break;
    for (const m of [...marks].reverse()) {
      s = s.slice(0, m.start) + s.slice(m.innerStart, m.innerEnd) + s.slice(m.end);
    }
  }
  s = s.replace(new RegExp(`==(${NOTE_HL_KIND}):`, 'gi'), '');
  return s.replace(/(^|[^=])==(?!=)/g, '$1');
}

/** 管道表 / ASCII 框线:整行包 == 会拆结构,预览漏语法或当表格。 */
function isStructuralLine(line: string): boolean {
  const t = line.trim();
  if (!t) return false;
  if (/^[+┌├└┬┴][-─=━]{2,}/.test(t)) return true;
  if (/^[+=\-─━]{4,}$/.test(t)) return true;
  if (/^[|│]/.test(t)) return true;
  return false;
}

function wrapHighlightLine(line: string, tone: NoteHlTone): string {
  if (parseFenceLine(line) || isStructuralLine(line)) return line;
  const { prefix, rest } = splitBlockPrefix(line);
  if (isStructuralLine(rest)) return line;
  const body = flattenTonedMarkup(rest);
  if (!body.trim()) return prefix + body;
  const parsed = parseNoteHighlight(body);
  if (parsed) {
    if (parsed.tone === tone) return prefix + body;
    if (!parsed.inner.includes('==')) return prefix + wrapNoteHighlight(parsed.inner, tone);
  }
  if (body.includes('==')) return prefix + body;
  return prefix + wrapNoteHighlight(body, tone);
}

function parseFenceLine(line: string): { char: string; length: number; rest: string } | null {
  const m = FENCE_OPEN.exec(line);
  if (!m) return null;
  return { char: m[2][0], length: m[2].length, rest: m[3] };
}

/** 扫描 ==tone:…==;tonedOnly=false 时兼认裸 ==…==(旧笔记)。 */
export function scanMarks(text: string, tonedOnly = false): NoteMarkSpan[] {
  const out: NoteMarkSpan[] = [];
  let i = 0;
  const n = text.length;
  while (i < n - 1) {
    if (text[i] !== '=' || text[i + 1] !== '=') {
      i += 1;
      continue;
    }
    let tone: NoteHlTone = 'warm';
    let innerStart = i + 2;
    let toned = false;
    const hit = readToneAt(text, i + 2);
    if (hit) {
      tone = hit.tone;
      innerStart = hit.innerStart;
      toned = true;
    }
    if (tonedOnly && !toned) {
      i += 1;
      continue;
    }
    const close = text.indexOf('==', innerStart);
    if (close < 0) {
      i += 1;
      continue;
    }
    if (close === innerStart) {
      i = close;
      continue;
    }
    out.push({ start: i, innerStart, innerEnd: close, end: close + 2, tone });
    i = close + 2;
  }
  return out;
}

function inRanges(ranges: { start: number; end: number }[], idx: number): boolean {
  return ranges.some((r) => idx >= r.start && idx < r.end);
}

/** CommonMark 行内代码:`…` / `` … ``,不跨围栏;未闭合的开口不当保护区间。 */
function inlineCodeRanges(content: string, fences: { start: number; end: number }[]): { start: number; end: number }[] {
  const ranges: { start: number; end: number }[] = [];
  const n = content.length;
  let i = 0;
  while (i < n) {
    if (inRanges(fences, i) || content[i] !== '`') {
      i += 1;
      continue;
    }
    let run = 1;
    while (i + run < n && content[i + run] === '`') run += 1;
    let j = i + run;
    let found = false;
    while (j < n) {
      if (inRanges(fences, j)) break;
      if (content[j] === '`') {
        let m = 1;
        while (j + m < n && content[j + m] === '`') m += 1;
        if (m === run) {
          ranges.push({ start: i, end: j + m });
          i = j + m;
          found = true;
          break;
        }
        j += m;
        continue;
      }
      j += 1;
    }
    if (!found) i += run;
  }
  return ranges;
}

function protectedRanges(content: string): { start: number; end: number }[] {
  const fences = fenceRanges(content);
  return [...fences, ...inlineCodeRanges(content, fences)].sort((a, b) => a.start - b.start);
}

function fenceRanges(content: string): { start: number; end: number }[] {
  const ranges: { start: number; end: number }[] = [];
  const n = content.length;
  let pos = 0;
  let inFence = false;
  let start = 0;
  let marker = '';
  let minLen = 0;
  while (pos <= n) {
    const nl = content.indexOf('\n', pos);
    const lineEnd = nl < 0 ? n : nl;
    const parsed = parseFenceLine(content.slice(pos, lineEnd));
    if (parsed) {
      if (!inFence) {
        inFence = true;
        marker = parsed.char;
        minLen = parsed.length;
        start = pos;
      } else if (parsed.char === marker && parsed.length >= minLen && parsed.rest.trim() === '') {
        ranges.push({ start, end: lineEnd });
        inFence = false;
      }
    }
    if (nl < 0) break;
    pos = nl + 1;
  }
  if (inFence) ranges.push({ start, end: n });
  return ranges;
}

/** 正文里的底纹区间;围栏与行内代码里的 == 当字面量。 */
export function findMarks(content: string): NoteMarkSpan[] {
  const fences = protectedRanges(content);
  if (fences.length === 0) return scanMarks(content, true);
  const out: NoteMarkSpan[] = [];
  let pos = 0;
  for (const f of fences) {
    if (f.start > pos) {
      for (const m of scanMarks(content.slice(pos, f.start), true)) {
        out.push({
          start: m.start + pos,
          innerStart: m.innerStart + pos,
          innerEnd: m.innerEnd + pos,
          end: m.end + pos,
          tone: m.tone,
        });
      }
    }
    pos = f.end;
  }
  if (pos < content.length) {
    for (const m of scanMarks(content.slice(pos), true)) {
      out.push({
        start: m.start + pos,
        innerStart: m.innerStart + pos,
        innerEnd: m.innerEnd + pos,
        end: m.end + pos,
        tone: m.tone,
      });
    }
  }
  return out;
}

function buildSpans(doc: string): TextSpan[] {
  const fences = fenceRanges(doc);
  const marks = findMarks(doc);
  const spans: TextSpan[] = [];
  const n = doc.length;
  let pos = 0;
  let fi = 0;
  let mi = 0;
  while (pos < n) {
    const fence = fi < fences.length && fences[fi].start === pos ? fences[fi] : null;
    if (fence) {
      spans.push({ kind: 'fence', start: fence.start, end: fence.end, tone: null });
      pos = fence.end;
      fi += 1;
      continue;
    }
    const mark = mi < marks.length && marks[mi].start === pos ? marks[mi] : null;
    if (mark) {
      spans.push({ kind: 'text', start: mark.innerStart, end: mark.innerEnd, tone: mark.tone });
      pos = mark.end;
      mi += 1;
      continue;
    }
    let next = n;
    if (fi < fences.length) next = Math.min(next, fences[fi].start);
    if (mi < marks.length) next = Math.min(next, marks[mi].start);
    spans.push({ kind: 'text', start: pos, end: next, tone: null });
    pos = next;
  }
  return spans.filter((s) => s.end > s.start);
}

function splitSpans(spans: TextSpan[], points: number[]): TextSpan[] {
  const cuts = [...new Set(points)].sort((a, b) => a - b);
  const out: TextSpan[] = [];
  for (const s of spans) {
    if (s.kind === 'fence') {
      out.push(s);
      continue;
    }
    const inner = cuts.filter((p) => p > s.start && p < s.end);
    let a = s.start;
    for (const p of inner) {
      out.push({ kind: 'text', start: a, end: p, tone: s.tone });
      a = p;
    }
    out.push({ kind: 'text', start: a, end: s.end, tone: s.tone });
  }
  return out.filter((s) => s.end > s.start);
}

function emitSpans(doc: string, spans: TextSpan[], clearRange?: { from: number; to: number }): string {
  type Group =
    | { kind: 'fence'; span: TextSpan }
    | { kind: 'text'; tone: NoteHlTone | null; chunks: TextSpan[] };
  const groups: Group[] = [];
  for (const s of spans) {
    if (s.kind === 'fence') {
      groups.push({ kind: 'fence', span: s });
      continue;
    }
    const last = groups[groups.length - 1];
    if (last && last.kind === 'text' && last.tone === s.tone) {
      last.chunks.push(s);
    } else {
      groups.push({ kind: 'text', tone: s.tone, chunks: [s] });
    }
  }
  return groups
    .map((g) => {
      if (g.kind === 'fence') {
        const raw = doc.slice(g.span.start, g.span.end);
        if (clearRange && g.span.end > clearRange.from && g.span.start < clearRange.to) {
          return stripAllMarks(raw);
        }
        return raw;
      }
      const text = g.chunks.map((c) => doc.slice(c.start, c.end)).join('');
      if (!g.tone) {
        if (clearRange && g.chunks.some((c) => c.end > clearRange.from && c.start < clearRange.to)) {
          return stripAllMarks(text);
        }
        return text;
      }
      return text.split('\n').map((line) => wrapHighlightLine(line, g.tone as NoteHlTone)).join('\n');
    })
    .join('');
}

function hasWrappable(doc: string, s: TextSpan): boolean {
  if (s.kind !== 'text' || s.end <= s.start) return false;
  return doc
    .slice(s.start, s.end)
    .split('\n')
    .some((line) => splitBlockPrefix(line).rest.trim().length > 0 && !line.includes('=='));
}

function unwrapMark(doc: string, m: NoteMarkSpan): string {
  return doc.slice(0, m.start) + doc.slice(m.innerStart, m.innerEnd) + doc.slice(m.end);
}

function wrapInner(inner: string, tone: NoteHlTone): string {
  return inner.split('\n').map((line) => wrapHighlightLine(line, tone)).join('\n');
}

function stripAllMarks(text: string): string {
  let s = text;
  for (let n = 0; n < 32; n += 1) {
    const marks = scanMarks(s, true);
    if (marks.length === 0) break;
    for (const m of [...marks].reverse()) {
      s = s.slice(0, m.start) + s.slice(m.innerStart, m.innerEnd) + s.slice(m.end);
    }
  }
  // 未闭合的 ==tone: 残留(架构图按行写入却没写成对);不剥裸 ==,以免改代码字面量
  return s.replace(new RegExp(`==(${NOTE_HL_KIND}):`, 'gi'), '');
}

function intervalTransform(doc: string, from: number, to: number, action: NoteHlAction): string {
  const spans = splitSpans(buildSpans(doc), [from, to]);
  const inside = spans.filter((s) => s.kind === 'text' && s.start >= from && s.end <= to);
  const already =
    action !== 'clear' &&
    inside.some((s) => hasWrappable(doc, s)) &&
    inside.every((s) => !hasWrappable(doc, s) || s.tone === action);
  for (const s of spans) {
    if (s.kind === 'fence') continue;
    if (s.start >= from && s.end <= to) {
      if (action === 'clear' || already) s.tone = null;
      else s.tone = action;
    }
  }
  return emitSpans(doc, spans, action === 'clear' ? { from, to } : undefined);
}

/** 在全文 [from,to) 上着色或清除;围栏不动;套住已有底纹时先拆平再包。 */
export function applyNoteHighlightInDoc(doc: string, from: number, to: number, action: NoteHlAction): string {
  const text = doc.replace(/\r\n/g, '\n');
  let a = Math.max(0, Math.min(from, to));
  let b = Math.min(text.length, Math.max(from, to));
  if (a === b) return text;
  const inlines = inlineCodeRanges(text, fenceRanges(text));
  if (inlines.some((r) => r.start <= a && b <= r.end)) return text;
  const marks = findMarks(text);
  const containers = marks.filter((m) => m.start <= a && b <= m.end);
  if (containers.length === 1) {
    const m = containers[0];
    const inInner = m.innerStart <= a && b <= m.innerEnd;
    const proper = a > m.innerStart || b < m.innerEnd;
    if (inInner && proper && action !== 'clear' && action !== m.tone) {
      const left = text.slice(m.innerStart, a);
      const mid = text.slice(a, b);
      const right = text.slice(b, m.innerEnd);
      const pieces = [
        left ? wrapInner(left, m.tone) : '',
        wrapInner(mid, action),
        right ? wrapInner(right, m.tone) : '',
      ];
      return text.slice(0, m.start) + pieces.join('') + text.slice(m.end);
    }
    if (action === 'clear' || action === m.tone) {
      return unwrapMark(text, m);
    }
    return text.slice(0, m.start) + wrapInner(text.slice(m.innerStart, m.innerEnd), action) + text.slice(m.end);
  }
  return intervalTransform(text, a, b, action);
}

/** 把一段独立文本当全文处理(工具栏切片 / flatten 仍可用)。 */
export function applyNoteHighlight(selected: string, action: NoteHlAction): string {
  const text = selected.replace(/\r\n/g, '\n');
  return applyNoteHighlightInDoc(text, 0, text.length, action);
}

export function toggleNoteHighlight(selected: string, tone: NoteHlTone): string {
  return applyNoteHighlight(selected, tone);
}

/** 选区恰好是某段底纹的 inner 时扩到整段标记,便于同色再点去掉。 */
export function expandHighlightRange(doc: string, from: number, to: number): { from: number; to: number } {
  const selected = doc.slice(from, to);
  if (parseNoteHighlight(selected)) return { from, to };
  const m = findMarks(doc).find((x) => x.innerStart === from && x.innerEnd === to);
  if (m) return { from: m.start, to: m.end };
  return { from, to };
}

/** 渲染前把旧的跨段 ==tone:a\\n\\nb== 拆成每行一条。 */
export function flattenMultilineMarks(md: string): string {
  const marks = findMarks(md);
  let out = md;
  for (const m of [...marks].reverse()) {
    const inner = out.slice(m.innerStart, m.innerEnd);
    if (!inner.includes('\n')) continue;
    out = out.slice(0, m.start) + wrapInner(inner, m.tone) + out.slice(m.end);
  }
  return out;
}

function markNode(tone: NoteHlTone, children: MdNode[]): MdNode {
  const className = isRgbTone(tone) ? ['notes-hl-rgb', `notes-hl-${tone}`] : [`notes-hl-${tone}`];
  return {
    type: 'mark',
    data: { hName: 'mark', hProperties: { className } },
    children,
  };
}

/** 把一行(无跨节点)里的 ==tone:text== 切成文本/mark;单测与退化路径用。 */
export function splitMarkedText(value: string): MdNode[] {
  const marks = scanMarks(value);
  if (marks.length === 0) return [{ type: 'text', value }];
  const out: MdNode[] = [];
  let last = 0;
  for (const m of marks) {
    if (m.start > last) out.push({ type: 'text', value: value.slice(last, m.start) });
    out.push(markNode(m.tone, [{ type: 'text', value: value.slice(m.innerStart, m.innerEnd) }]));
    last = m.end;
  }
  if (last < value.length) out.push({ type: 'text', value: value.slice(last) });
  return out.length ? out : [{ type: 'text', value }];
}

function splitTextAt(value: string, locals: number[]): string[] {
  const pts = [...new Set(locals.filter((p) => p > 0 && p < value.length))].sort((a, b) => a - b);
  if (pts.length === 0) return [value];
  const parts: string[] = [];
  let prev = 0;
  for (const p of pts) {
    parts.push(value.slice(prev, p));
    prev = p;
  }
  parts.push(value.slice(prev));
  return parts.filter((p) => p.length > 0);
}

function wrapMarksInChildren(parent: MdNode): void {
  const children = parent.children;
  if (!children?.length) return;

  type Span = { kind: 'text' | 'atom'; index: number; absStart: number; absEnd: number; value?: string };
  const spans: Span[] = [];
  let abs = 0;
  for (let i = 0; i < children.length; i += 1) {
    const c = children[i];
    if (c.type === 'text' && typeof c.value === 'string') {
      spans.push({ kind: 'text', index: i, absStart: abs, absEnd: abs + c.value.length, value: c.value });
      abs += c.value.length;
    } else {
      spans.push({ kind: 'atom', index: i, absStart: abs, absEnd: abs + 1 });
      abs += 1;
    }
  }
  const concat = spans.map((s) => (s.kind === 'text' ? s.value ?? '' : OBJECT_CHAR)).join('');
  const marks = scanMarks(concat);
  if (marks.length === 0) return;

  const cuts = new Map<number, number[]>();
  const addCut = (absPos: number) => {
    for (const s of spans) {
      if (s.kind !== 'text' || s.value == null) continue;
      if (absPos >= s.absStart && absPos <= s.absEnd) {
        const local = absPos - s.absStart;
        const arr = cuts.get(s.index) ?? [];
        arr.push(local);
        cuts.set(s.index, arr);
        return;
      }
    }
  };
  for (const m of marks) {
    addCut(m.start);
    addCut(m.innerStart);
    addCut(m.innerEnd);
    addCut(m.end);
  }

  const flat: MdNode[] = [];
  const flatAbs: { absStart: number; absEnd: number }[] = [];
  for (let i = 0; i < children.length; i += 1) {
    const c = children[i];
    const span = spans[i];
    if (c.type === 'text' && typeof c.value === 'string' && cuts.has(i)) {
      let local = 0;
      for (const part of splitTextAt(c.value, cuts.get(i) ?? [])) {
        flat.push({ type: 'text', value: part });
        flatAbs.push({ absStart: span.absStart + local, absEnd: span.absStart + local + part.length });
        local += part.length;
      }
    } else {
      flat.push(c);
      flatAbs.push({ absStart: span.absStart, absEnd: span.absEnd });
    }
  }

  const out: MdNode[] = [];
  let i = 0;
  while (i < flat.length) {
    const hit = marks.find((m) => flatAbs[i].absStart === m.start && flatAbs[i].absEnd === m.innerStart);
    if (!hit) {
      out.push(flat[i]);
      i += 1;
      continue;
    }
    const inner: MdNode[] = [];
    let k = i + 1;
    while (k < flat.length && flatAbs[k].absStart < hit.innerEnd) {
      inner.push(flat[k]);
      k += 1;
    }
    if (inner.length) out.push(markNode(hit.tone, inner));
    i = k < flat.length && flatAbs[k].absStart === hit.innerEnd ? k + 1 : k;
  }
  parent.children = out;
}

function walk(node: MdNode): void {
  if (node.type === 'code' || node.type === 'inlineCode' || !node.children) return;
  for (const child of node.children) walk(child);
  wrapMarksInChildren(node);
}

/** remark 插件:只改笔记预览传入的插件列表,聊天渲染不启用。 */
export function remarkNoteMarks() {
  return (tree: MdNode) => {
    walk(tree);
  };
}

export const NOTE_PREVIEW_REMARK = [remarkNoteMarks];

/** 新旧文档的最小替换区间,给 CodeMirror 一次 dispatch。 */
export function diffReplace(oldText: string, next: string): { from: number; to: number; insert: string } {
  let a = 0;
  const max = Math.min(oldText.length, next.length);
  while (a < max && oldText[a] === next[a]) a += 1;
  let bOld = oldText.length;
  let bNew = next.length;
  while (bOld > a && bNew > a && oldText[bOld - 1] === next[bNew - 1]) {
    bOld -= 1;
    bNew -= 1;
  }
  return { from: a, to: bOld, insert: next.slice(a, bNew) };
}
