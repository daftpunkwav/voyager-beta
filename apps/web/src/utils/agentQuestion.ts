/**
 * Agent 反问/测验：归一化、兜底选项、从正文 JSON/Markdown 识别题目。
 *
 * §4.2.16 N-02 拆分：本文件作为"对外面"（即 `@/utils/agentQuestion`）的稳定
 * 入口，自身不再持有实现，仅 re-export 子模块。所有现有
 * `import { ... } from '@/utils/agentQuestion'` 行为不变。
 *
 * 子模块（位于 ./agentQuestion/）:
 *   - constants.ts       共享兜底选项（LEVEL / LANG / GOAL）
 *   - radio-helpers.ts   isPlaceholderOptions / stripOptionLetterPrefix /
 *                        formatRadioOptionLabel + 内部 helper
 *   - text-cleanup.ts    cleanQuestionText / parseLetterOptions /
 *                        cleanOptions / isAskUserShapedText
 *   - parsers.ts         extractAskUserFromText / extractMarkdownQuiz /
 *                        recoverQuestionFromText
 *   - hydrate.ts         ensureAgentQuestion / hydrateAgentMessages /
 *                        tryParseAnswerDump
 *   - quiz.ts            isExamQuestion / questionTitle
 *   - card-formatters.ts formatAnswersForCard / formatMemoryChipContent
 *
 * 历史：原 715 行单文件已拆为 7 个职责清晰的子模块。
 */

export {
  isPlaceholderOptions,
  stripOptionLetterPrefix,
  formatRadioOptionLabel,
} from './agentQuestion/radio-helpers';
export {
  cleanQuestionText,
  parseLetterOptions,
  cleanOptions,
  isAskUserShapedText,
} from './agentQuestion/text-cleanup';
export {
  extractAskUserFromText,
  extractMarkdownQuiz,
  recoverQuestionFromText,
} from './agentQuestion/parsers';
export {
  ensureAgentQuestion,
  hydrateAgentMessages,
  tryParseAnswerDump,
} from './agentQuestion/hydrate';
export { isExamQuestion, questionTitle } from './agentQuestion/quiz';
export {
  formatAnswersForCard,
  formatMemoryChipContent,
} from './agentQuestion/card-formatters';
