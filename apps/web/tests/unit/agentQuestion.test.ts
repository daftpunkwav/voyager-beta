import { describe, expect, it } from 'vitest';
import {
  cleanOptions,
  ensureAgentQuestion,
  extractAskUserFromText,
  extractMarkdownQuiz,
  formatAnswersForCard,
  recoverQuestionFromText,
} from '@/utils/agentQuestion';

describe('cleanOptions', () => {
  it('解析标准数组', () => {
    const opts = cleanOptions([
      { value: 'a', label: 'RunnableSequence 链式组合' },
      { value: 'b', label: '仅语法糖无实际对象' },
    ]);
    expect(opts).toHaveLength(2);
    expect(opts[0]?.label).toMatch(/RunnableSequence/);
  });

  it('拒绝假「选项 A」占位并返回空（交由上层改文本题）', () => {
    const opts = cleanOptions([
      { value: 'a', label: '选项 A' },
      { value: 'b', label: '选项 B' },
      { value: 'c', label: '选项 C' },
      { value: 'd', label: '选项 D' },
    ], 'LCEL 流水线本质是？', 'q1');
    expect(opts).toHaveLength(0);
  });

  it('从 description 提升为选项正文', () => {
    const opts = cleanOptions([
      { value: 'A', description: 'RunnableSequence 的简写' },
      { value: 'B', description: '仅仅是语法糖' },
    ]);
    expect(opts).toHaveLength(2);
    expect(opts[0]?.label).toMatch(/RunnableSequence/);
  });

  it('解析字母键字典', () => {
    const opts = cleanOptions({ A: '从未接触', B: '写过 Demo', C: '能改功能' });
    expect(opts.length).toBeGreaterThanOrEqual(3);
    expect(opts.map((o) => o.value)).toContain('A');
  });

  it('拒绝字符拆分数组并走题干兜底', () => {
    const opts = cleanOptions(['r', 'í', 'a'], '你的编程水平大致处于哪个阶段?', 'q1');
    expect(opts.length).toBeGreaterThanOrEqual(3);
    expect(opts.every((o) => o.label.length > 1)).toBe(true);
  });

  it('拒绝字符索引对象', () => {
    const opts = cleanOptions(
      { '0': 'r', '1': 'í', '2': 'a' },
      'ReAct 循环顺序是？',
      'q1'
    );
    expect(opts.every((o) => (o.label || '').length > 1)).toBe(true);
  });

  it('解析 A/B/C 多行字符串', () => {
    const opts = cleanOptions(
      'A. Thought→Action→Observation\nB. Action→Observation→Thought\nC. Observation→Thought→Action'
    );
    expect(opts).toHaveLength(3);
    expect(opts[0]?.value).toBe('A');
    expect(opts[0]?.label).toMatch(/Thought/);
  });

  it('空选项时按题干兜底', () => {
    const opts = cleanOptions([], '你的编程水平大致处于哪个阶段?', 'q1');
    expect(opts.length).toBeGreaterThanOrEqual(3);
    expect(opts.some((o) => /初学|了解|掌握/.test(o.label))).toBe(true);
  });
});

describe('extractMarkdownQuiz', () => {
  it('从正文 Markdown 选择题提取交互题', () => {
    const text = `
第 2 题 / 5: Tool / Function Calling 的本质

题目：当 LLM "调用一个工具" 时，底层实际发生的是什么？

- **A.** LLM 在自己的神经网络里执行 Python 代码
- **B.** LLM 输出结构化文本 (JSON / 函数签名)，由宿主程序解析后真正去执行外部函数
- **C.** LLM 通过系统调用直接访问操作系统 API
- **D.** LLM 把请求转发给另一个独立的 LLM 实例去处理

请直接选 A / B / C / D 回复，我出第 3 题。
`;
    const q = extractMarkdownQuiz(text);
    expect(q).not.toBeNull();
    expect(q!.questions).toHaveLength(1);
    const item = q!.questions[0]!;
    expect(item.type).toBe('radio');
    if (item.type === 'radio') {
      expect(item.options.length).toBe(4);
      expect(item.options[1]?.label).toMatch(/结构化文本|JSON/);
      expect(item.exam).toBe(true);
      expect(item.allow_other).toBe(false);
    }
  });
});

describe('recoverQuestionFromText', () => {
  it('优先 JSON，其次 Markdown', () => {
    const json = JSON.stringify({
      title: '摸底',
      items: [
        { id: 'q1', type: 'single_choice', prompt: '水平?', options: ['初级', '中级', '高级'] },
      ],
    });
    expect(recoverQuestionFromText(json)?.questions[0]?.text).toContain('水平');
  });
});

describe('ensureAgentQuestion', () => {
  it('从 ask_user items 生成可渲染结构', () => {
    const q = ensureAgentQuestion({
      title: '课前摸底',
      items: [
        {
          id: 'q1',
          type: 'single_choice',
          prompt: '你的编程水平?',
          options: [],
        },
        {
          id: 'q2',
          type: 'quiz',
          prompt: 'ReAct 循环顺序?',
          options: { A: 'T→A→O', B: 'A→T→O', C: 'O→A→T' },
        },
      ],
    });
    expect(q).not.toBeNull();
    expect(q!.questions).toHaveLength(2);
    expect(q!.questions[0]!.type).toBe('radio');
    expect((q!.questions[0] as { options: unknown[] }).options.length).toBeGreaterThanOrEqual(2);
    expect((q!.questions[1] as { exam?: boolean }).exam).toBe(true);
  });

  it('损坏的单字符 options 改为可填写，禁止假 ABCD', () => {
    const q = ensureAgentQuestion({
      title: 'Agent 基础测验 - 第 1 题 / 5',
      items: [
        {
          id: 'q1',
          type: 'quiz',
          prompt: 'ReAct 框架中典型顺序？',
          options: ['r', 'í', 'a'],
        },
      ],
    });
    expect(q).not.toBeNull();
    const item = q!.questions[0]!;
    expect(item.type).toBe('radio');
    if (item.type === 'radio') {
      expect(item.options.some((o) => /自由填写|选项未能解析/.test(o.label) || o.value === 'other')).toBe(
        true
      );
      expect(item.allow_other).toBe(true);
      expect(item.options.every((o) => !/^选项\s*[A-D]$/.test(o.label))).toBe(true);
    }
  });
});

describe('extractAskUserFromText', () => {
  it('从正文 JSON 识别反问', () => {
    const raw = JSON.stringify({
      title: '摸底',
      items: [
        { id: 'q1', type: 'single_choice', prompt: '水平?', options: ['初级', '中级', '高级'] },
      ],
    });
    const q = extractAskUserFromText(raw);
    expect(q).not.toBeNull();
    expect(q!.questions[0]!.text).toContain('水平');
  });
});

describe('formatAnswersForCard', () => {
  it('按 question_id 对齐答案', () => {
    const q = ensureAgentQuestion({
      title: '测',
      items: [
        { id: 'q1', type: 'single_choice', prompt: 'Q1', options: ['A选项', 'B选项'] },
        { id: 'q2', type: 'single_choice', prompt: 'Q2', options: ['C选项', 'D选项'] },
      ],
    })!;
    const formatted = formatAnswersForCard(q, [
      { type: 'radio', value: 'B选项', question_id: 'q1' },
      { type: 'radio', value: 'C选项', question_id: 'q2' },
    ]);
    expect(formatted.details[0]?.answer).toMatch(/B/);
    expect(formatted.details[1]?.answer).toMatch(/C/);
    expect(formatted.summary).toBe('已答 2 题');
  });
});
