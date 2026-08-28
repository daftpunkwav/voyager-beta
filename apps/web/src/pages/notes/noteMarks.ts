/** 笔记底纹:Markdown 标记 ==tone:text==,不是富文本。用户工具栏与 agent mark_note_span 同语法。 */

export const NOTE_HL_TONES = ['warm', 'cool', 'rose', 'lime'] as const;
export type NoteHlTone = (typeof NOTE_HL_TONES)[number];
export type NoteHlAction = NoteHlTone | 'clear';

export const NOTE_HL_LABEL: Record<NoteHlTone, string> = {
  warm: '暖黄底纹',
  cool: '冷蓝底纹',
  rose: '玫红底纹',
  lime: '青绿底纹',
};

const TONE_SET = new Set<string>(NOTE_HL_TONES);
const MARK_TOKEN = /==(?:(warm|cool|rose|lime):)?((?:(?!==)[\s\S])+?)==/g;

interface MdNode {
  type: string;
  value?: string;
  children?: MdNode[];
  data?: { hName?: string; hProperties?: Record<string, unknown> };
}

export function parseNoteHighlight(text: string): { tone: NoteHlTone; inner: string } | null {
  if (!text) return null;
  const token = /^==(warm|cool|rose|lime):([\s\S]*)==$/.exec(text);
  if (token) return { tone: token[1] as NoteHlTone, inner: token[2] };
  const bare = /^==([\s\S]*)==$/.exec(text);
  if (!bare) return null;
  const inner = bare[1];
  for (const t of NOTE_HL_TONES) {
    const prefix = `${t}:`;
    if (inner.startsWith(prefix)) return { tone: t, inner: inner.slice(prefix.length) };
  }
  return { tone: 'warm', inner };
}

export function wrapNoteHighlight(inner: string, tone: NoteHlTone): string {
  return `==${tone}:${inner}==`;
}

/** 若光标在底纹内侧,把区间扩到整段 ==tone:…==,避免叠套。 */
export function expandHighlightRange(doc: string, from: number, to: number): { from: number; to: number } {
  const selected = doc.slice(from, to);
  if (parseNoteHighlight(selected)) return { from, to };
  if (doc.slice(to, to + 2) !== '==') return { from, to };
  for (const t of NOTE_HL_TONES) {
    const prefix = `==${t}:`;
    if (from >= prefix.length && doc.slice(from - prefix.length, from) === prefix) {
      return { from: from - prefix.length, to: to + 2 };
    }
  }
  if (from >= 2 && doc.slice(from - 2, from) === '==') {
    return { from: from - 2, to: to + 2 };
  }
  return { from, to };
}

export function toggleNoteHighlight(selected: string, tone: NoteHlTone): string {
  const parsed = parseNoteHighlight(selected);
  if (parsed?.tone === tone) return parsed.inner;
  const inner = parsed?.inner ?? selected;
  if (!inner || inner.includes('==')) return selected;
  return wrapNoteHighlight(inner, tone);
}

export function applyNoteHighlight(selected: string, action: NoteHlAction): string {
  if (action === 'clear') return parseNoteHighlight(selected)?.inner ?? selected;
  return toggleNoteHighlight(selected, action);
}

/** 把一行里的 ==tone:text== 切成 mdast 文本/mark 节点。 */
export function splitMarkedText(value: string): MdNode[] {
  const re = new RegExp(MARK_TOKEN.source, 'g');
  const out: MdNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null = re.exec(value);
  while (m) {
    if (m.index > last) out.push({ type: 'text', value: value.slice(last, m.index) });
    const tone = m[1] && TONE_SET.has(m[1]) ? (m[1] as NoteHlTone) : 'warm';
    out.push({
      type: 'mark',
      data: { hName: 'mark', hProperties: { className: [`notes-hl-${tone}`] } },
      children: [{ type: 'text', value: m[2] }],
    });
    last = m.index + m[0].length;
    m = re.exec(value);
  }
  if (last < value.length) out.push({ type: 'text', value: value.slice(last) });
  return out.length ? out : [{ type: 'text', value }];
}

function walk(node: MdNode): void {
  if (node.type === 'code' || node.type === 'inlineCode' || !node.children) return;
  const next: MdNode[] = [];
  for (const child of node.children) {
    if (child.type === 'text' && child.value?.includes('==')) {
      next.push(...splitMarkedText(child.value));
    } else {
      walk(child);
      next.push(child);
    }
  }
  node.children = next;
}

/** remark 插件:只改笔记预览传入的插件列表,聊天渲染不启用。 */
export function remarkNoteMarks() {
  return (tree: MdNode) => {
    walk(tree);
  };
}

export const NOTE_PREVIEW_REMARK = [remarkNoteMarks];
