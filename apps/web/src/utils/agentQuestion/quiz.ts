/**
 * 测验判定与标题抽取（§4.2.16 N-02 拆分）。
 *
 * 含:
 *   - isExamLike      私有: 仅"测验/考试/第 N 题"等明确语义才算 exam
 *   - isExamQuestion  公开: 整组 `AgentQuestion` 是否含有任一 exam 单选
 *   - questionTitle   公开: 从 `intro.content` 抽取标题（去掉加粗符号）
 */
import type { AgentQuestion } from '@/api/types';

/** 仅明确「测验/考试」语义才标 exam;普通选择题澄清不算测验 */
function isExamLike(prompt: string, qtype: string, title = ''): boolean {
  if (qtype === 'quiz') return true;
  return /测验|考试|小测试|考考你|掌握度|第\s*\d+\s*题/.test(`${prompt} ${title}`);
}

/** 整组 AgentQuestion 是否含有任一 exam 单选 */
export function isExamQuestion(q: AgentQuestion): boolean {
  return q.questions.some((item) => item.type === 'radio' && item.exam);
}

/** 从 intro.content 抽取展示用标题（去掉 markdown 加粗符号 / 默认占位） */
export function questionTitle(q: AgentQuestion): string {
  return (q.intro?.content ?? '结构化反问').replace(/\*\*/g, '').trim() || '结构化反问';
}

// 暴露 isExamLike 给 hydrate.ts 使用，避免循环依赖
export const __quizInternal = { isExamLike };
