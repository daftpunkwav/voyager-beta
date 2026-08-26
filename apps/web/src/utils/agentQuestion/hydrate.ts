/**
 * 数据归一化与水合（§4.2.16 N-02 拆分）。
 *
 * 含:
 *   - ensureAgentQuestion  归一化: `{title, items, allow_skip}` ↔ `AgentQuestion`
 *   - normalizeItem        私有:  单个 `{prompt, options, type}` → QuestionItem
 *   - hydrateAgentMessages 水合:  会话消息列表 → 渲染友好的 question/answer 卡片
 *   - tryParseAnswerDump   反规范化: 泄漏在聊天/偏好的答案 JSON → QuestionAnswerRecord
 *
 * 注意 ensureAgentQuestion 与 parsers.ts 存在循环依赖（hydrate → parsers → hydrate），
 * 双方均在函数体内调用对方，ESM 运行时安全。如需彻底消除，
 * 可将 recoverQuestionFromText 从 parsers 内联到 hydrate.ts。
 */
import type {
  AgentMessage,
  AgentQuestion,
  QuestionAnswer,
  QuestionAnswerRecord,
  QuestionItem,
} from '@/api/types';
import { LEVEL_OPTS } from './constants';
import { isPlaceholderOptions } from './radio-helpers';
import { cleanQuestionText, cleanOptions } from './text-cleanup';
import { __quizInternal, questionTitle } from './quiz';
import { recoverQuestionFromText } from './parsers';

const { isExamLike } = __quizInternal;

/**
 * 把后端 AgentQuestion 或原始 ask_user 参数统一成可渲染结构。
 * 两个分支:
 *   - 已是前端 AgentQuestion（带 question_id + questions 数组）→ 重整选项 + 文案
 *   - 原始 ask_user `{title, items, allow_skip}` → 标准化 + 兜底补 LEVEL_OPTS
 */
export function ensureAgentQuestion(raw: unknown, _agentId = 'hub'): AgentQuestion | null {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;

  // 已是前端结构
  if (Array.isArray(obj.questions) && obj.question_id) {
    const q = obj as unknown as AgentQuestion;
    const title = questionTitle(q);
    const generic = new Set(['请回答以下问题', '请选择', '请选择最符合的一项', '']);
    return {
      ...q,
      questions: q.questions.map((item) => {
        if (item.type === 'radio') {
          const opts = cleanOptions(item.options, item.text, item.id);
          const exam =
            typeof item.exam === 'boolean'
              ? item.exam
              : isExamLike(item.text, 'single_choice', title);
          if (opts.length < 2 || isPlaceholderOptions(opts)) {
            return {
              ...item,
              text: cleanQuestionText(
                /选项未能解析/.test(item.text)
                  ? item.text
                  : `${item.text}\n\n（选项未能解析，请直接填写你的答案）`
              ),
              options: [{ value: 'other', label: '自由填写（在下方输入）' }],
              exam: false,
              allow_other: true,
            };
          }
          let text = cleanQuestionText(item.text);
          if (generic.has(text.trim()) || text.trim() === title.trim()) {
            const labels = opts.map((o) => o.label).join(' ');
            if (/初学|了解|掌握|精通/.test(labels)) {
              text = '你的编程 / 技术掌握水平大致处于哪个阶段？';
            } else if (/Python|TypeScript|Go|Rust/.test(labels)) {
              text = '你更熟悉 / 想用哪一类技术栈？';
            } else {
              text = '请选择最符合你情况的一项：';
            }
          }
          return {
            ...item,
            text,
            options: opts,
            exam,
            allow_other: exam ? false : item.allow_other,
          };
        }
        if (item.type === 'checkbox') {
          const opts = cleanOptions(
            item.options.map((o) => ({ value: o.value, label: o.text })),
            item.text,
            item.id
          );
          return {
            ...item,
            text: cleanQuestionText(item.text),
            options: opts.map((o) => ({ value: o.value, text: o.label })),
          };
        }
        return { ...item, text: cleanQuestionText(item.text) };
      }),
    };
  }

  // 原始 ask_user：{ title, items, allow_skip }
  const items = obj.items;
  if (!Array.isArray(items) && !obj.title) return null;

  const title = String(obj.title ?? '请回答以下问题');
  const list = Array.isArray(items) ? items : [];
  const questions = list
    .filter((x): x is Record<string, unknown> => Boolean(x) && typeof x === 'object')
    .map((it, i) => normalizeItem(it, i, title));

  if (questions.length === 0) {
    questions.push({
      id: 'default',
      text: '你的编程 / 技术掌握水平大致处于哪个阶段？',
      type: 'radio',
      options: LEVEL_OPTS,
      allow_other: true,
    });
  } else {
    const generic = new Set(['请回答以下问题', '请选择', '请选择最符合的一项', '']);
    for (const q of questions) {
      const text = (q.text || '').trim();
      if (text && !generic.has(text) && text !== title.trim()) continue;
      const labels =
        q.type === 'radio'
          ? q.options.map((o) => o.label).join(' ')
          : q.type === 'checkbox'
            ? q.options.map((o) => o.text).join(' ')
            : '';
      if (/初学|了解|掌握|精通/.test(labels)) {
        q.text = '你的编程 / 技术掌握水平大致处于哪个阶段？';
      } else if (/Python|TypeScript|Go|Rust/.test(labels)) {
        q.text = '你更熟悉 / 想用哪一类技术栈？';
      } else if (generic.has(text) || text === title.trim()) {
        q.text = '请选择最符合你情况的一项：';
      }
    }
  }

  const allowSkip = obj.allow_skip !== false;
  return {
    question_id: String(obj.question_id ?? `q_${Date.now()}`),
    intro: { type: 'markdown', content: `**${title}**` },
    questions,
    actions: {
      submit: { text: '提交', style: 'primary' },
      skip: allowSkip ? { text: '跳过', style: 'ghost' } : undefined,
    },
    allow_skip: allowSkip,
    timeout: null,
  };
}

/** 单个 `{prompt, options, type}` 字典 → QuestionItem（含 checkbox/slider/text 分支） */
function normalizeItem(
  raw: Record<string, unknown>,
  index: number,
  title = ''
): QuestionItem {
  const id = String(raw.id ?? `q_${index + 1}`);
  const prompt = cleanQuestionText(
    String(raw.prompt ?? raw.text ?? raw.question ?? '请选择')
  );
  const qtype = String(raw.type ?? 'single_choice').toLowerCase();
  const rawOpts = raw.options ?? raw.choices ?? raw.answers ?? [];
  const opts = cleanOptions(rawOpts, prompt, id);
  const exam = isExamLike(prompt, qtype, title);

  if (qtype === 'multi_choice' || qtype === 'checkbox') {
    if (opts.length < 2) {
      return {
        id,
        text: `${prompt}\n\n（选项未能解析，请直接填写）`,
        type: 'radio',
        options: [{ value: 'other', label: '自由填写（在下方输入）' }],
        allow_other: true,
      };
    }
    return {
      id,
      text: prompt,
      type: 'checkbox',
      options: opts.map((o) => ({ value: o.value, text: o.label })),
    };
  }
  if (qtype === 'scale' || qtype === 'slider') {
    return {
      id,
      text: prompt,
      type: 'slider',
      min: Number(raw.min ?? 0),
      max: Number(raw.max ?? 100),
      labels: (raw.labels as Record<string, string>) ?? { '0': '不懂', '100': '精通' },
    };
  }
  if (qtype === 'text' && !exam) {
    return {
      id,
      text: prompt,
      type: 'radio',
      options: [{ value: 'other', label: '自由填写（在下方输入）' }],
      allow_other: true,
    };
  }
  // 单选 / quiz：禁止假「选项 A」；解析失败则改为可填写
  if (opts.length < 2 || isPlaceholderOptions(opts)) {
    return {
      id,
      text: `${prompt}\n\n（选项未能解析，请直接填写你的答案）`,
      type: 'radio',
      options: [{ value: 'other', label: '自由填写（在下方输入）' }],
      allow_other: true,
      exam: false,
    };
  }
  return {
    id,
    text: prompt,
    type: 'radio',
    options: opts,
    allow_other: !exam,
    exam,
  };
}

/** 将会话 API 消息水合为可渲染的 question / question_answer 卡片 */
export function hydrateAgentMessages(messages: AgentMessage[]): AgentMessage[] {
  return messages.map((m) => {
    if (m.question) {
      return { ...m, question: ensureAgentQuestion(m.question) ?? m.question };
    }
    if (m.question_answer?.question) {
      const q = ensureAgentQuestion(m.question_answer.question) ?? m.question_answer.question;
      return { ...m, question_answer: { ...m.question_answer, question: q } };
    }
    if (m.role === 'assistant' && m.content) {
      const recovered = recoverQuestionFromText(m.content);
      if (recovered) {
        return {
          ...m,
          question: recovered,
          content: `发起反问：${questionTitle(recovered)}`,
        };
      }
    }
    if (m.role === 'user' && m.content) {
      const ans = tryParseAnswerDump(m.content);
      if (ans) return { ...m, question_answer: ans, content: `[反问回答] ${ans.summary}` };
    }
    return m;
  });
}

/**
 * 把泄漏到聊天/偏好里的答案 JSON 收成可读摘要。
 * 支持:
 *   - 数组形态 `[{type, value, question_id}]`
 *   - 字典形态 `{q1: {type, value}, q2: 'a'}`
 *   - 带 `[反问回答]` 前缀的文本
 */
export function tryParseAnswerDump(text: string): QuestionAnswerRecord | null {
  const raw = text.replace(/^\[反问回答\]\s*/, '').trim();
  if (!raw.startsWith('{') && !raw.startsWith('[')) return null;
  try {
    const parsed = JSON.parse(raw) as unknown;
    const answers: QuestionAnswer[] = [];
    if (Array.isArray(parsed)) {
      for (const item of parsed) {
        if (item && typeof item === 'object' && 'type' in (item as object)) {
          answers.push(item as QuestionAnswer);
        }
      }
    } else if (parsed && typeof parsed === 'object') {
      for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
        if (v && typeof v === 'object' && 'type' in (v as object)) {
          answers.push({
            ...(v as QuestionAnswer),
            question_id: (v as QuestionAnswer).question_id ?? k,
          });
        } else if (typeof v === 'string' || typeof v === 'number') {
          answers.push({ type: 'radio', value: String(v), question_id: k });
        }
      }
    }
    if (answers.length === 0) return null;
    const details = answers.map((a, i) => ({
      question: `第 ${i + 1} 题`,
      answer: summarizeOneAnswer(a),
    }));
    const summary =
      details.length <= 3
        ? details.map((d) => d.answer).join(' · ')
        : `已回答 ${details.length} 题`;
    return {
      question: {
        question_id: 'recovered',
        intro: { type: 'markdown', content: '历史回答' },
        questions: answers.map((a, i) => ({
          id: a.question_id ?? `q_${i}`,
          text: `第 ${i + 1} 题`,
          type: 'radio' as const,
          options: [],
        })),
        actions: { submit: { text: '提交', style: 'primary' } },
        allow_skip: true,
        timeout: null,
      },
      answers,
      summary,
      details,
    };
  } catch {
    return null;
  }
}

/** 单条答案摘要（用于 tryParseAnswerDump 内的格式化） */
function summarizeOneAnswer(a: QuestionAnswer): string {
  if (a.type === 'radio') return a.other_text?.trim() || a.value || '（未答）';
  if (a.type === 'checkbox') return a.values.join('、') || '（未答）';
  if (a.type === 'slider') return String(a.value);
  if (a.type === 'drag_sort') return a.order.join(' → ');
  if (a.type === 'knowledge_map') return a.checked.join('、');
  return '（已答）';
}
