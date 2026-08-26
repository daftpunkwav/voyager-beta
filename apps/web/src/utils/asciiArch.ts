/**
 * 识别「含边框的 ASCII 架构图」并解析为层级，避免中英混排等宽错位。
 * 注意：不得误伤 Markdown 管道表格（| col | col |）。
 */

export interface AsciiArchLayer {
  title: string;
  lines: string[];
}

/** GFM 表头分隔行：|---|---| 或 | :--- | ---: | */
function isMarkdownTableSeparator(line: string): boolean {
  const t = line.trim();
  if (!t.includes('-') || !t.includes('|')) return false;
  // 去掉单元格后应几乎只剩 | : - 空白
  const stripped = t.replace(/[\s|:-]/g, '');
  return stripped.length === 0 && (t.match(/\|/g) ?? []).length >= 2;
}

/** 多列表格行（至少两根竖线分隔） */
function isMarkdownTableRow(line: string): boolean {
  const t = line.trim();
  if (!t.includes('|')) return false;
  const pipes = (t.match(/\|/g) ?? []).length;
  // | a | b | → 至少 2 个 |
  return pipes >= 2;
}

export function looksLikeMarkdownTable(text: string): boolean {
  const lines = text
    .replace(/\r\n/g, '\n')
    .trim()
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length < 2) return false;
  const sepIdx = lines.findIndex(isMarkdownTableSeparator);
  if (sepIdx < 0) return false;
  // 分隔行上下应有表格行
  const headerLine = lines[sepIdx - 1];
  const hasHeader = sepIdx > 0 && headerLine !== undefined && isMarkdownTableRow(headerLine);
  const bodyRows = lines.slice(sepIdx + 1).filter(isMarkdownTableRow);
  return hasHeader && (bodyRows.length >= 1 || lines.length <= 3);
}

function isBoxBorderLine(line: string): boolean {
  const t = line.trim();
  if (!t) return false;
  // +---+ / ┌─┐ / ├─┤（真正的框线，不是 |---|---| 表格分隔）
  if (/^[+┌├└┬┴][-─=━]{2,}[+┐┤┘]?$/.test(t)) return true;
  if (/^[┌├└][─\s]{2,}[┐┤┘]$/.test(t)) return true;
  if (/^[+=\-─━]{4,}$/.test(t)) return true;
  return false;
}

function stripBoxPadding(line: string): string {
  return line
    .replace(/^\s*[|│]\s?/, '')
    .replace(/\s*[|│]\s*$/, '')
    .replace(/\s+$/g, '');
}

function looksLikeAsciiBox(text: string): boolean {
  if (looksLikeMarkdownTable(text)) return false;

  const lines = text.replace(/\r\n/g, '\n').trim().split('\n');
  if (lines.length < 4) return false;

  let borders = 0;
  let pipeContent = 0;
  for (const line of lines) {
    if (isBoxBorderLine(line)) {
      borders += 1;
      continue;
    }
    // 单侧框线内容行：| .... | 或 | ....（右侧可不齐）
    const t = line.trim();
    if (/^[|│]/.test(t) && !isMarkdownTableSeparator(t)) {
      // 表格行通常有 ≥2 个 | 且像单元格；框内容行也常有左右 |
      // 若整段已排除 markdown table，这里允许
      pipeContent += 1;
    }
  }
  // 必须有真正的 +--- / ┌─ 类边框，不能只靠 | 行
  return borders >= 2 && pipeContent >= 2;
}

/**
 * 尝试把 ASCII 边框图解析为层级列表；不像框图则返回 null。
 */
export function tryParseAsciiArchLayers(text: string): AsciiArchLayer[] | null {
  const raw = text.replace(/\r\n/g, '\n').trim();
  if (!raw || !looksLikeAsciiBox(raw)) return null;

  const lines = raw.split('\n');
  const layers: AsciiArchLayer[] = [];
  let bucket: string[] = [];

  const flush = () => {
    const cleaned = bucket
      .map(stripBoxPadding)
      .map((l) => l.trimEnd())
      .filter((l) => l.trim().length > 0);
    bucket = [];
    if (!cleaned.length) return;
    const title = cleaned[0]?.trim() ?? '';
    const rest = cleaned.slice(1).map((l) => l.trim()).filter(Boolean);
    layers.push({ title, lines: rest });
  };

  for (const line of lines) {
    if (isBoxBorderLine(line)) {
      flush();
      continue;
    }
    if (/^\s*[|│]/.test(line) || bucket.length > 0) {
      bucket.push(line);
    }
  }
  flush();

  if (layers.length < 2) return null;
  return layers;
}
