/**
 * 文本清洗与选项规范化（§4.2.16 N-02 拆分）。
 *
 * 含:
 *   - cleanQuestionText          清理题干泄漏的 markdown fence / 反引号
 *   - parseLetterOptions         从多行文本解析 A/B/C/D 选项
 *   - cleanOptions               统一从 string/array/object/字符拆分字典 等
 *                                异常形态中抽可读 RadioOption[]
 *   - isAskUserShapedText        判定一段正文是否是反问（含 JSON / Markdown）
 *
 * 原文件把「选项清洗部分」和「文本清洗部分」混在 cleanOptions 里。这里保留
 * cleanOptions 的对外 API 不变，但内部依赖 radio-helpers 提供
 * isPlaceholderOptions / __radioInternal 等复用 helper。
 */
import type { RadioOption } from '@/api/types';
import {
  __radioInternal,
  isPlaceholderOptions,
  stripOptionLetterPrefix,
} from './radio-helpers';

/**
 * 清理题干中泄漏的 markdown fence / 反引号。
 * 全部清空时回退到「（题目文本缺失）」占位文案。
 */
export function cleanQuestionText(text: string): string {
  let t = String(text ?? '').trim();
  t = t.replace(/^```(?:[\w+-]*)?\s*\n?/, '').replace(/\n?```\s*$/, '').trim();
  t = t.replace(/^`{1,3}\s*/, '').replace(/\s*`{1,3}$/, '').trim();
  if (!t || /^`{1,3}$/.test(t)) return '（题目文本缺失）';
  return t;
}

/**
 * 从多行文本解析 A/B/C/D 选项。
 * 同时兼容 **A.**、- A、A、 等多种写法。
 */
export function parseLetterOptions(text: string): RadioOption[] {
  const out: RadioOption[] = [];
  const re =
    /(?:^|\n)\s*(?:[-*•]\s*)?(?:\*\*)?([A-Da-d])(?:\*\*)?[.、)）：:]\s*(.+?)(?=(?:\n\s*(?:[-*•]\s*)?(?:\*\*)?[A-Da-d](?:\*\*)?[.、)）：:])|\n\n|$)/gs;
  let m: RegExpExecArray | null;
  const seen = new Set<string>();
  while ((m = re.exec(text)) !== null) {
    if (!m[1] || !m[2]) continue;
    const letter = m[1].toUpperCase();
    const label = stripOptionLetterPrefix(m[2].replace(/\*\*/g, '').trim());
    if (!label || seen.has(letter)) continue;
    seen.add(letter);
    out.push({ value: letter, label });
  }
  return out;
}

/**
 * 从任意模型输出形态抽出可读 RadioOption[]。
 *
 * - string: 优先按 A/B/C 行解析；失败时退化为 JSON / 行分隔 / 逗号分隔；
 * - array:  防护「字符被拆成数组」；合法 ['A','B','C'] 保留；
 * - object: 防护「字符索引对象」{0:'r',1:'í',2:'a'}；保留键值对字典；
 *
 * 收尾时若 out 仍像字符拆分 / 假 ABCD 占位，则尝试从题干里抠
 * A/B/C，否则按 prompt 关键字返回 defaultOptionsFor 兜底。
 */
export function cleanOptions(raw: unknown, prompt = '', id = ''): RadioOption[] {
  let list: unknown[] = [];

  if (typeof raw === 'string') {
    const t = raw.trim();
    // 优先按 A/B/C 行解析
    const letterOpts = parseLetterOptions(t);
    if (letterOpts.length >= 2) {
      return letterOpts;
    }
    if (t.startsWith('[')) {
      try {
        const parsed = JSON.parse(t) as unknown;
        if (Array.isArray(parsed)) list = parsed;
      } catch {
        list = t.split(/[,，;；|]/).map((s) => s.trim()).filter(Boolean);
      }
    } else if (t.includes('\n')) {
      list = t.split(/\n/).map((s) => s.trim()).filter(Boolean);
    } else if (t) {
      // 无分隔的整句：当作单一候选，后面用兜底补齐
      list = t.split(/[,，;；|]/).map((s) => s.trim()).filter(Boolean);
    }
  } else if (Array.isArray(raw)) {
    // 防护：字符串被展开成字符数组；保留合法 ['A','B','C']
    if (
      raw.length >= 2 &&
      raw.every((x) => typeof x === 'string' && (x as string).length <= 1) &&
      !raw.every((x) => typeof x === 'string' && /^[A-Da-d]$/.test(x as string))
    ) {
      list = [];
    } else {
      list = raw;
    }
  } else if (raw && typeof raw === 'object') {
    const entries = Object.entries(raw as Record<string, unknown>);
    // 防护：{"0":"r","1":"í","2":"a"} 字符索引对象
    if (
      entries.length >= 2 &&
      entries.every(
        ([k, v]) => /^\d+$/.test(k) && typeof v === 'string' && (v as string).length <= 1
      )
    ) {
      list = [];
    } else {
      list = entries.map(([k, v]) => {
        if (v && typeof v === 'object') return v;
        return { value: k, label: String(v ?? k) };
      });
    }
  }

  const out: RadioOption[] = [];
  for (const o of list) {
    if (o == null) continue;
    if (typeof o === 'string' || typeof o === 'number') {
      const s = String(o).trim();
      if (!s) continue;
      const m = s.match(/^([A-Da-d])[.、)）：:\s]+\s*(.+)$/);
      if (m?.[1] && m[2]) {
        out.push({
          value: m[1].toUpperCase(),
          label: stripOptionLetterPrefix(m[2].trim()),
        });
      } else {
        out.push({ value: s, label: stripOptionLetterPrefix(s) });
      }
      continue;
    }
    if (typeof o === 'object') {
      // 嵌套数组 ["A", "描述"]
      if (Array.isArray(o)) {
        if (o.length >= 2) {
          const letter = String(o[0]).trim();
          const label = stripOptionLetterPrefix(String(o[1]).trim());
          if (label) {
            out.push({
              value: /^[A-Da-d]$/.test(letter) ? letter.toUpperCase() : letter,
              label,
            });
          }
        }
        continue;
      }
      const obj = o as Record<string, unknown>;
      let label = String(
        obj.label ??
          obj.text ??
          obj.name ??
          obj.content ??
          obj.desc ??
          obj.description ??
          obj.answer ??
          obj.option ??
          obj.choice ??
          obj.body ??
          ''
      ).trim();
      let value = String(obj.value ?? obj.id ?? obj.key ?? '').trim();
      // 仅有 A–D 题号时，尝试把 description 提成正文
      if (
        (!label || (/^[A-Da-d]$/.test(label) && label === value)) &&
        obj.description
      ) {
        label = String(obj.description).trim();
      }
      if (!label && !value) {
        const entries = Object.entries(obj).filter(
          ([k]) => !['correct', 'is_correct', 'score'].includes(k)
        );
        if (entries.length === 1 && entries[0]) {
          value = entries[0][0];
          label = String(entries[0][1] ?? '').trim();
        } else if (
          entries.length >= 1 &&
          entries.every(([k]) => /^[A-Da-d]$/i.test(k))
        ) {
          // {"A":"文案"} 单键对象
          const head = entries[0];
          if (!head) continue;
          const [k, v] = head;
          value = k.toUpperCase();
          label = String(v ?? '').trim();
        }
      }
      if (!label && value) label = value;
      if (!value && label) value = label;
      if (!label && !value) continue;
      label = stripOptionLetterPrefix(label);
      // 丢弃无意义的单字符（除非只是 A/B/C/D 字母题号且无更好标签——仍太短则跳过）
      if (label.length <= 1 && !/^[A-Da-d]$/.test(label)) continue;
      // 纯题号无正文：跳过，留给题干解析 / 文本题兜底
      if (/^[A-Da-d]$/.test(label) && (!obj.description || label === value)) {
        continue;
      }
      const opt: RadioOption = { value, label };
      if (obj.description && String(obj.description) !== label) {
        opt.description = String(obj.description);
      }
      out.push(opt);
    }
  }

  const { looksLikeCharSplit, defaultOptionsFor } = __radioInternal;
  if (looksLikeCharSplit(out) || out.length < 2 || isPlaceholderOptions(out)) {
    // 尝试从题干里抠 A/B/C
    const fromPrompt = parseLetterOptions(prompt);
    if (fromPrompt.length >= 2 && !isPlaceholderOptions(fromPrompt)) {
      return fromPrompt;
    }
    const defaults = defaultOptionsFor(prompt, id);
    if (defaults.length >= 2) return defaults;
    return out.length >= 2 && !isPlaceholderOptions(out) ? out : [];
  }
  return out;
}

/**
 * 判定一段助手正文是否包含反问（JSON 形态或 Markdown 选择题）。
 * 仅做粗筛——实际解析交给 recoverQuestionFromText。
 *
 * 注意:除"以 JSON 开头"的形态外,也覆盖"文本中间嵌入 JSON 子串"的场景,
 * 对齐旧 `extractAskUserFromText` 的 start/end 分支,避免 UI 重复展示
 * (说明文字 + 中间 JSON 反问时,若判为非反问,会被保留为独立 assistant 消息)。
 */
export function isAskUserShapedText(text: string): boolean {
  if (!text) return false;
  const trimmed = text.trim();
  // 1. 开头即是 JSON 形态
  if (
    (trimmed.startsWith('{') || trimmed.startsWith('[')) &&
    (/"items"\s*:|"questions"\s*:|"options"\s*:/).test(trimmed)
  ) {
    return true;
  }
  // 2. 文本中间嵌入的 JSON 子串(对齐旧 extractAskUserFromText 的 start/end 分支,
  //    避免"说明文字 + 中间 JSON 反问"场景下 UI 重复展示)
  const start = trimmed.indexOf('{');
  const end = trimmed.lastIndexOf('}');
  if (start >= 0 && end > start) {
    const slice = trimmed.slice(start, end + 1);
    if (/"items"\s*:|"questions"\s*:/.test(slice)) return true;
  }
  // 3. Markdown 选择题
  if (
    parseLetterOptions(trimmed).length >= 2 &&
    /(?:题目[：:]|请选择|选出|测验|小测试|正确答案|第\s*\d+\s*题)/.test(trimmed)
  ) {
    return true;
  }
  return false;
}
