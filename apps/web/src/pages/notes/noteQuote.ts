/** 笔记预览选区:压空白、截断、交给侦察人格的讲解稿。 */

export const NOTES_QUOTE_MAX = 500;

/** 预览里拖选的词/句:压空白、截断。空串表示没有有效选区。 */
export function parseNotesQuote(raw: string | null | undefined): string {
  return String(raw ?? '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, NOTES_QUOTE_MAX);
}

let lastExplainQuote = '';

export function rememberNotesQuote(quote: string): void {
  lastExplainQuote = parseNotesQuote(quote);
}

export function lastNotesExplainQuote(): string {
  return lastExplainQuote;
}

/** 讲解请求的用户可见正文。agentName 由调用方传入显示名,本文件不绑具体人格。 */
export function buildNoteExplainMessage(opts: {
  quote: string;
  agentName: string;
  title?: string;
}): string {
  const quote = parseNotesQuote(opts.quote);
  const who = (opts.agentName || '').trim() || '助手';
  const title = (opts.title || '').trim().slice(0, 80);
  const where = title ? `《${title}》` : '这篇笔记';
  return (
    `${who}，请快速解读我在笔记${where}标出的内容：\n\n` +
    `「${quote}」\n\n` +
    `一两句话说明它是什么、在这篇里为什么出现。不要展开成课，不要重写整篇。`
  );
}
