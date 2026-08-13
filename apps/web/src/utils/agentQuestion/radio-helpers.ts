/**
 * 单选 / 选项格式化 helper（§4.2.16 N-02 拆分）。
 *
 * 含:
 *   - `isPlaceholderOptions`     占位选项检测（假 ABCD）
 *   - `looksLikeCharSplit`        字符被错误拆分的检测（私有）
 *   - `defaultOptionsFor`         关键字匹配的兜底选项（私有）
 *   - `stripOptionLetterPrefix`   剥离选项文案已有的 A./B、 等题号
 *   - `formatRadioOptionLabel`    统一成「A. 文案」展示形式
 *
 * `cleanOptions` 跨模块需要它，但自身拆到了 `text-cleanup.ts` 一侧
 * 的「选项清洗部分」；为保持原 export 行为不变，函数主入口仍留在原文件，
 * 这里只暴露纯函数 helper。
 */
import type { RadioOption } from '@/api/types';
import { GOAL_OPTS, LANG_OPTS, LEVEL_OPTS } from './constants';

/**
 * 无意义的占位选项（解析失败时的假 ABCD）。
 * 检测到 ≥ 2 个「选项 A」「选项 B」就视为假占位。
 */
export function isPlaceholderOptions(opts: RadioOption[]): boolean {
  if (opts.length < 2) return false;
  const placeholders = opts.filter((o) =>
    /^选项\s*[A-Da-d]$/u.test((o.label || o.value || '').trim())
  );
  return placeholders.length >= Math.min(2, opts.length);
}

/**
 * 检测是否被错误地按字符拆开（如 "ría" → r/í/a）；
 * 合法 A–D 题号不算字符拆分。
 */
function looksLikeCharSplit(opts: RadioOption[]): boolean {
  if (opts.length < 2) return false;
  const allLetterKeys = opts.every((o) =>
    /^[A-Da-d]$/.test((o.label || o.value).trim())
  );
  if (allLetterKeys && opts.length <= 8) return false;
  const short = opts.filter((o) => (o.label || o.value).trim().length <= 1);
  return short.length >= Math.ceil(opts.length * 0.6);
}

/** 关键字命中时返回对应兜底选项；测验类不返回假 ABCD */
function defaultOptionsFor(prompt: string, id: string): RadioOption[] {
  const key = `${id} ${prompt}`.toLowerCase();
  if (/水平|level|掌握|熟练|程度|阶段/.test(key)) return LEVEL_OPTS;
  if (/语言|language|tech|技术栈|熟悉|常用/.test(key)) return LANG_OPTS;
  if (/想做|目标|goal|这次|目的|来这里|主要想/.test(key)) return GOAL_OPTS;
  // 测验类不再返回假「选项 A」——交由调用方改文本题或从题干解析
  return [];
}

/**
 * 去掉选项文案上已有的 A. / B、 等题号前缀，避免 UI 再拼一次。
 * 失败时回退到原文本，避免出现空字符串。
 */
export function stripOptionLetterPrefix(label: string): string {
  const t = label.trim();
  const stripped = t.replace(/^[A-Da-d][.、)）：:]\s*/u, '').trim();
  return stripped || t;
}

/**
 * 展示用：统一成「A. 文案」，不重复字母。
 * - value 已是 A-D 时优先用 value；
 * - 否则按 index % 26 生成字母；
 * - body 与字母完全一致时只返回字母，避免「A. A」这种冗余。
 */
export function formatRadioOptionLabel(
  option: { value: string; label?: string },
  index: number
): string {
  const letter = /^[A-Da-d]$/.test(option.value)
    ? option.value.toUpperCase()
    : String.fromCharCode(65 + (index % 26));
  const body = stripOptionLetterPrefix(option.label || option.value);
  if (!body) return letter;
  if (body.toUpperCase() === letter) return letter;
  return `${letter}. ${body}`;
}

// 私有 helper 通过 export-as-internal 暴露给 `text-cleanup.ts` 的
// `cleanOptions` 使用，避免循环依赖与重复实现。
export const __radioInternal = { looksLikeCharSplit, defaultOptionsFor };
