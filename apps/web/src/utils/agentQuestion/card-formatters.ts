/**
 * 卡片格式化（§4.2.16 N-02 拆分）。
 *
 * 公开导出:
 *   - formatAnswersForCard     反问卡 + 聊天卡片的"已答 N 题"摘要与详情列表
 *   - formatMemoryChipContent  侧栏记忆芯片：避免直接展示答题 JSON
 *
 * 文件内私有 helper:
 *   - labelForRadio     radio 答案 → "A. 文案"（复用 radio-helpers.formatRadioOptionLabel）
 *   - labelForCheckbox  checkbox 答案 → "文案"
 *
 * 行为完全对齐原 `agentQuestion.ts`（§4.2.16 拆分第一步中的 formatters.ts
 * 用 "A · 文案" 拼接口径不同，本文件以原文件为准）。
 */
import type { AgentQuestion, QuestionAnswer, QuestionItem } from '@/api/types';
import { formatRadioOptionLabel } from './radio-helpers';
import { tryParseAnswerDump } from './hydrate';

/** radio 答案 → "A. 文案"，与 formatRadioOptionLabel 行为一致 */
function labelForRadio(qi: QuestionItem, value: string): string {
  if (qi.type !== 'radio') return value;
  const opt = qi.options.find((o) => o.value === value);
  if (!opt) return value;
  const idx = qi.options.findIndex((o) => o.value === value);
  return formatRadioOptionLabel(opt, idx >= 0 ? idx : 0);
}

/** checkbox 答案 → 多个文案 join */
function labelForCheckbox(qi: QuestionItem, value: string): string {
  if (qi.type !== 'checkbox') return value;
  return qi.options.find((o) => o.value === value)?.text ?? value;
}

/**
 * 反问卡 / 聊天卡片的答卷摘要与详情。
 * - summary 保持短（避免"已答 A·B·C"挤一行）
 * - details 完整列出每道题的真实回答，便于点开展示
 */
export function formatAnswersForCard(
  question: AgentQuestion,
  answers: QuestionAnswer[]
): { summary: string; details: { question: string; answer: string }[] } {
  const details: { question: string; answer: string }[] = [];
  question.questions.forEach((qi, idx) => {
    const a = answers.find((x) => x.question_id === qi.id) ?? answers[idx];
    let answer = '（未答）';
    if (a) {
      if (a.type === 'radio') answer = a.other_text?.trim() || labelForRadio(qi, a.value);
      else if (a.type === 'checkbox') answer = a.values.map((v) => labelForCheckbox(qi, v)).join('、');
      else if (a.type === 'slider') answer = String(a.value);
      else if (a.type === 'drag_sort') answer = a.order.join(' → ');
      else if (a.type === 'knowledge_map') answer = a.checked.join('、');
    }
    details.push({ question: qi.text, answer });
  });
  // 卡片摘要保持短；完整选项进详情，避免一行挤满 A·B·C
  const answered = details.filter((d) => d.answer && d.answer !== '（未答）').length;
  const summary =
    answered === 0
      ? '未作答'
      : answered === 1
        ? details.find((d) => d.answer && d.answer !== '（未答）')?.answer ?? `已答 1 题`
        : `已答 ${answered} 题`;
  return { summary, details };
}

/** 侧栏记忆芯片：避免直接展示答题 JSON */
export function formatMemoryChipContent(content: string): string {
  const t = content.trim();
  if (!t) return content;
  if ((t.startsWith('{') || t.startsWith('[')) && /"type"\s*:|"value"\s*:/.test(t)) {
    const recovered = tryParseAnswerDump(t);
    if (recovered) return `答题偏好 · ${recovered.summary}`;
    return '学习偏好（结构化记录）';
  }
  if (t.length > 80) return `${t.slice(0, 77)}…`;
  return content;
}
