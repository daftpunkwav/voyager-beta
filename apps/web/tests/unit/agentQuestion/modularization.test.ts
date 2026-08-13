/**
 * §4.2.16 N-02 拆分验证:
 *  1. 每个子模块核心 export 至少 1-2 个基础断言
 *  2. 通过 `@/utils/agentQuestion` 重新 export 的符号 === 子模块直接 export 的符号
 *  3. 关键函数边界(isPlaceholderOptions / formatRadioOptionLabel /
 *     cleanQuestionText / extractAskUserFromText / ensureAgentQuestion /
 *     formatMemoryChipContent)各 ≥ 1 个
 */

import { describe, it, expect } from 'vitest';

import * as AgentQuestion from '@/utils/agentQuestion';
import * as RadioHelpers from '@/utils/agentQuestion/radio-helpers';
import * as TextCleanup from '@/utils/agentQuestion/text-cleanup';
import * as Parsers from '@/utils/agentQuestion/parsers';
import * as Hydrate from '@/utils/agentQuestion/hydrate';
import * as Quiz from '@/utils/agentQuestion/quiz';
import * as CardFormatters from '@/utils/agentQuestion/card-formatters';
import * as Constants from '@/utils/agentQuestion/constants';

describe('agentQuestion 模块化(§4.2.16 N-02)', () => {
  describe('子模块 export 完整性', () => {
    it('radio-helpers 暴露 3 个公开符号', () => {
      expect(typeof RadioHelpers.isPlaceholderOptions).toBe('function');
      expect(typeof RadioHelpers.stripOptionLetterPrefix).toBe('function');
      expect(typeof RadioHelpers.formatRadioOptionLabel).toBe('function');
    });
    it('text-cleanup 暴露 4 个公开符号', () => {
      expect(typeof TextCleanup.cleanQuestionText).toBe('function');
      expect(typeof TextCleanup.parseLetterOptions).toBe('function');
      expect(typeof TextCleanup.cleanOptions).toBe('function');
      expect(typeof TextCleanup.isAskUserShapedText).toBe('function');
    });
    it('parsers 暴露 3 个公开符号', () => {
      expect(typeof Parsers.extractAskUserFromText).toBe('function');
      expect(typeof Parsers.extractMarkdownQuiz).toBe('function');
      expect(typeof Parsers.recoverQuestionFromText).toBe('function');
    });
    it('hydrate 暴露 3 个公开符号', () => {
      expect(typeof Hydrate.ensureAgentQuestion).toBe('function');
      expect(typeof Hydrate.hydrateAgentMessages).toBe('function');
      expect(typeof Hydrate.tryParseAnswerDump).toBe('function');
    });
    it('quiz 暴露 2 个公开符号', () => {
      expect(typeof Quiz.isExamQuestion).toBe('function');
      expect(typeof Quiz.questionTitle).toBe('function');
    });
    it('card-formatters 暴露 2 个公开符号', () => {
      expect(typeof CardFormatters.formatAnswersForCard).toBe('function');
      expect(typeof CardFormatters.formatMemoryChipContent).toBe('function');
    });
    it('constants 暴露 3 个常量', () => {
      expect(Array.isArray(Constants.LEVEL_OPTS)).toBe(true);
      expect(Constants.LEVEL_OPTS.length).toBe(4);
      expect(Array.isArray(Constants.LANG_OPTS)).toBe(true);
      expect(Array.isArray(Constants.GOAL_OPTS)).toBe(true);
    });
  });

  describe('re-export 引用相等(拆分但仍是同一函数)', () => {
    it('isPlaceholderOptions === 子模块版本', () => {
      expect(AgentQuestion.isPlaceholderOptions).toBe(RadioHelpers.isPlaceholderOptions);
    });
    it('stripOptionLetterPrefix === 子模块版本', () => {
      expect(AgentQuestion.stripOptionLetterPrefix).toBe(RadioHelpers.stripOptionLetterPrefix);
    });
    it('formatRadioOptionLabel === 子模块版本', () => {
      expect(AgentQuestion.formatRadioOptionLabel).toBe(RadioHelpers.formatRadioOptionLabel);
    });
    it('cleanQuestionText === 子模块版本', () => {
      expect(AgentQuestion.cleanQuestionText).toBe(TextCleanup.cleanQuestionText);
    });
    it('cleanOptions === 子模块版本', () => {
      expect(AgentQuestion.cleanOptions).toBe(TextCleanup.cleanOptions);
    });
    it('isAskUserShapedText === 子模块版本', () => {
      expect(AgentQuestion.isAskUserShapedText).toBe(TextCleanup.isAskUserShapedText);
    });
    it('parseLetterOptions === 子模块版本', () => {
      expect(AgentQuestion.parseLetterOptions).toBe(TextCleanup.parseLetterOptions);
    });
    it('extractAskUserFromText === 子模块版本', () => {
      expect(AgentQuestion.extractAskUserFromText).toBe(Parsers.extractAskUserFromText);
    });
    it('extractMarkdownQuiz === 子模块版本', () => {
      expect(AgentQuestion.extractMarkdownQuiz).toBe(Parsers.extractMarkdownQuiz);
    });
    it('recoverQuestionFromText === 子模块版本', () => {
      expect(AgentQuestion.recoverQuestionFromText).toBe(Parsers.recoverQuestionFromText);
    });
    it('ensureAgentQuestion === 子模块版本', () => {
      expect(AgentQuestion.ensureAgentQuestion).toBe(Hydrate.ensureAgentQuestion);
    });
    it('hydrateAgentMessages === 子模块版本', () => {
      expect(AgentQuestion.hydrateAgentMessages).toBe(Hydrate.hydrateAgentMessages);
    });
    it('tryParseAnswerDump === 子模块版本', () => {
      expect(AgentQuestion.tryParseAnswerDump).toBe(Hydrate.tryParseAnswerDump);
    });
    it('isExamQuestion === 子模块版本', () => {
      expect(AgentQuestion.isExamQuestion).toBe(Quiz.isExamQuestion);
    });
    it('questionTitle === 子模块版本', () => {
      expect(AgentQuestion.questionTitle).toBe(Quiz.questionTitle);
    });
    it('formatAnswersForCard === 子模块版本', () => {
      expect(AgentQuestion.formatAnswersForCard).toBe(CardFormatters.formatAnswersForCard);
    });
    it('formatMemoryChipContent === 子模块版本', () => {
      expect(AgentQuestion.formatMemoryChipContent).toBe(CardFormatters.formatMemoryChipContent);
    });
  });

  describe('isPlaceholderOptions 边界', () => {
    it('空数组 / 1 个元素 → false', () => {
      expect(RadioHelpers.isPlaceholderOptions([])).toBe(false);
      expect(RadioHelpers.isPlaceholderOptions([{ value: 'a', label: '选项 A' }])).toBe(false);
    });
    it('合法选项 → false', () => {
      expect(
        RadioHelpers.isPlaceholderOptions([
          { value: 'beginner', label: '初学' },
          { value: 'advanced', label: '掌握' },
        ])
      ).toBe(false);
    });
    it('≥2 个「选项 A/B」 → true', () => {
      expect(
        RadioHelpers.isPlaceholderOptions([
          { value: 'a', label: '选项 A' },
          { value: 'b', label: '选项 B' },
        ])
      ).toBe(true);
    });
    it('支持空格变体「选项  A」', () => {
      expect(
        RadioHelpers.isPlaceholderOptions([
          { value: 'a', label: '选项  A' },
          { value: 'b', label: '选项  B' },
          { value: 'c', label: '选项  C' },
        ])
      ).toBe(true);
    });
  });

  describe('formatRadioOptionLabel 边界', () => {
    it('value 已是 A-D 时优先用 value', () => {
      expect(
        RadioHelpers.formatRadioOptionLabel({ value: 'B', label: '写不动' }, 1)
      ).toBe('B. 写不动');
    });
    it('value 不是字母时按 index % 26 生成', () => {
      expect(RadioHelpers.formatRadioOptionLabel({ value: 'beginner', label: '初学' }, 0)).toBe(
        'A. 初学'
      );
      expect(RadioHelpers.formatRadioOptionLabel({ value: 'go', label: 'Go' }, 4)).toBe('E. Go');
    });
    it('body 与字母重复时省略 body', () => {
      expect(RadioHelpers.formatRadioOptionLabel({ value: 'A', label: 'A' }, 0)).toBe('A');
    });
    it('strip 已有前缀避免「A. A. 文案」', () => {
      expect(
        RadioHelpers.formatRadioOptionLabel({ value: 'A', label: 'A. RunnableSequence' }, 0)
      ).toBe('A. RunnableSequence');
    });
  });

  describe('cleanQuestionText 边界', () => {
    it('剥离首尾 markdown fence', () => {
      expect(TextCleanup.cleanQuestionText('```js\nWhat is LCEL?\n```')).toBe(
        'What is LCEL?'
      );
    });
    it('剥离单反引号对', () => {
      expect(TextCleanup.cleanQuestionText('`ReAct 是什么`')).toBe('ReAct 是什么');
    });
    it('全空回退到「（题目文本缺失）」', () => {
      expect(TextCleanup.cleanQuestionText('')).toBe('（题目文本缺失）');
      expect(TextCleanup.cleanQuestionText('```')).toBe('（题目文本缺失）');
    });
  });

  describe('extractAskUserFromText 边界', () => {
    it('裸 JSON 形态识别', () => {
      const raw = JSON.stringify({
        title: '摸底',
        items: [{ id: 'q1', type: 'single_choice', prompt: '水平?', options: ['A', 'B', 'C'] }],
      });
      const q = Parsers.extractAskUserFromText(raw);
      expect(q).not.toBeNull();
      expect(q!.questions[0]!.text).toContain('水平');
    });
    it('fence 包裹 JSON 形态识别', () => {
      const raw =
        '```json\n' +
        JSON.stringify({
          title: '摸底',
          items: [
            { id: 'q1', type: 'single_choice', prompt: '水平?', options: ['A', 'B', 'C'] },
          ],
        }) +
        '\n```';
      const q = Parsers.extractAskUserFromText(raw);
      expect(q).not.toBeNull();
    });
    it('普通文本 → null', () => {
      expect(Parsers.extractAskUserFromText('hi there')).toBeNull();
    });
  });

  describe('ensureAgentQuestion 边界', () => {
    it('null / 非对象 → null', () => {
      expect(Hydrate.ensureAgentQuestion(null)).toBeNull();
      expect(Hydrate.ensureAgentQuestion('garbage')).toBeNull();
      expect(Hydrate.ensureAgentQuestion(42)).toBeNull();
    });
    it('原始 ask_user 缺 items 与 title → null', () => {
      expect(Hydrate.ensureAgentQuestion({ foo: 'bar' })).toBeNull();
    });
    it('空 items 兜底 LEVEL_OPTS', () => {
      const q = Hydrate.ensureAgentQuestion({ title: '测' });
      expect(q).not.toBeNull();
      expect(q!.questions).toHaveLength(1);
      const item = q!.questions[0]!;
      expect(item.type).toBe('radio');
      if (item.type === 'radio') {
        expect(item.options.length).toBeGreaterThanOrEqual(4);
      }
    });
    it('单字符串 options 应改写为可填写', () => {
      const q = Hydrate.ensureAgentQuestion({
        title: '测验',
        items: [{ id: 'q1', type: 'quiz', prompt: '顺序?', options: ['r', 'i', 'a'] }],
      });
      expect(q).not.toBeNull();
      const item = q!.questions[0]!;
      if (item.type === 'radio') {
        expect(item.options.some((o) => o.value === 'other')).toBe(true);
        expect(item.allow_other).toBe(true);
      }
    });
  });

  describe('formatMemoryChipContent 边界', () => {
    it('短文本原样返回', () => {
      expect(CardFormatters.formatMemoryChipContent('hello world')).toBe('hello world');
    });
    it('超长文本截断为 77 字符 + 省略号', () => {
      const long = 'x'.repeat(120);
      const out = CardFormatters.formatMemoryChipContent(long);
      expect(out.length).toBeLessThanOrEqual(78);
      expect(out.endsWith('…')).toBe(true);
    });
    it('含 type/value 的 JSON 字符串 → 答题偏好', () => {
      const ans = JSON.stringify([{ type: 'radio', value: 'A', question_id: 'q1' }]);
      const out = CardFormatters.formatMemoryChipContent(ans);
      expect(out).toMatch(/^答题偏好/);
    });
    it('空字符串原样返回', () => {
      expect(CardFormatters.formatMemoryChipContent('')).toBe('');
    });
  });

  describe('isAskUserShapedText 边界(§4.2.16 拆分回归保护)', () => {
    it('纯 JSON 开头 → true', () => {
      expect(TextCleanup.isAskUserShapedText('{"items":[{"type":"radio"}]}')).toBe(true);
    });
    it('文本中间嵌入 JSON 反问 → true(捕获回归:防止"说明文字 + 中间 JSON"被漏判导致 UI 重复展示)', () => {
      expect(
        TextCleanup.isAskUserShapedText(
          '好的，我来问你：{"items":[{"type":"radio","options":["A","B"]}]}'
        )
      ).toBe(true);
    });
    it('含 A/B/C 选项 + 题目关键词 → true', () => {
      expect(TextCleanup.isAskUserShapedText('A.x\nB.y\nC.z\n第 1 题：选什么？')).toBe(true);
    });
    it('普通说明文本 → false', () => {
      expect(TextCleanup.isAskUserShapedText('我来帮你分析一下这个项目')).toBe(false);
    });
    it('空字符串 → false', () => {
      expect(TextCleanup.isAskUserShapedText('')).toBe(false);
    });
  });
});
