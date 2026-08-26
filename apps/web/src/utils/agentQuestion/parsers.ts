/**
 * 文本/Markdown 反问解析（§4.2.16 N-02 拆分）。
 *
 * 含:
 *   - extractAskUserFromText    从助手正文识别 ask_user JSON（裸 JSON / ```fence``` / 子串）
 *   - extractMarkdownQuiz        从 Markdown 正文识别「请选 A/B/C/D」式出题
 *   - recoverQuestionFromText    任意正文 → 结构化反问（JSON 优先，其次 Markdown）
 *
 * 这些函数都靠 ensureAgentQuestion 做最终归一化，自身只做"原始文本 → 半结构"。
 */
import type { AgentQuestion } from '@/api/types';
import { ensureAgentQuestion } from './hydrate';
import { parseLetterOptions } from './text-cleanup';

/**
 * 从助手正文中提取 ask_user JSON（模型未走工具时的兜底）。
 * 覆盖三种来源:
 *   - 整段 JSON（裸 or with ``` fence）
 *   - 文本中嵌入的子串 JSON（首个 `{}` 区间）
 */
export function extractAskUserFromText(text: string): AgentQuestion | null {
  if (!text) return null;
  const trimmed = text.trim();
  if (trimmed.startsWith('{') && /"items"\s*:|"questions"\s*:/.test(trimmed)) {
    try {
      return ensureAgentQuestion(JSON.parse(trimmed));
    } catch {
      /* continue */
    }
  }
  const fence = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fence?.[1]) {
    try {
      const q = ensureAgentQuestion(JSON.parse(fence[1].trim()));
      if (q) return q;
    } catch {
      /* continue */
    }
  }
  const start = trimmed.indexOf('{');
  const end = trimmed.lastIndexOf('}');
  if (start >= 0 && end > start) {
    const slice = trimmed.slice(start, end + 1);
    if (/"items"\s*:/.test(slice) || /"questions"\s*:/.test(slice)) {
      try {
        return ensureAgentQuestion(JSON.parse(slice));
      } catch {
        return null;
      }
    }
  }
  return null;
}

/**
 * 从 Markdown 正文识别「请选 A/B/C/D」式出题，转为交互弹窗。
 * 覆盖模型不调用 ask_user、直接在气泡里出题的情况。
 */
export function extractMarkdownQuiz(text: string): AgentQuestion | null {
  if (!text || text.length < 20) return null;
  const opts = parseLetterOptions(text);
  if (opts.length < 2) return null;

  // 需要有「题目」语气或明确要求作答
  const looksLikeQuiz =
    /第\s*\d+\s*题|题目[：:]|请直接选|请选择|选出|测验|小测试|正确答案|选项/.test(text) ||
    (/[A-D][.、)]/.test(text) && /[A-D][.、)]/.test(text.split('\n').slice(1).join('\n')));
  if (!looksLikeQuiz) return null;

  // 抽取题干：优先「题目：」后内容，否则取选项前最后一段非空行
  let prompt = '';
  const topic = text.match(/题目[：:]\s*(.+?)(?=\n|$)/);
  if (topic?.[1]) {
    prompt = topic[1].replace(/\*\*/g, '').trim();
  }
  if (!prompt) {
    const beforeOpts = text.split(/\n\s*(?:[-*•]\s*)?(?:\*\*)?[A-Da-d]/)[0] ?? text;
    const lines = beforeOpts
      .split('\n')
      .map((l) => l.replace(/^#+\s*/, '').replace(/\*\*/g, '').trim())
      .filter((l) => l && !/^[-—–]{2,}$/.test(l));
    prompt = lines[lines.length - 1] || '请选择正确答案';
  }

  const titleMatch = text.match(/(?:第\s*\d+\s*题\s*\/\s*\d+[：:]\s*)?([^\n]{4,40})/);
  const title =
    (text.match(/第\s*\d+\s*题\s*\/\s*\d+[：:]?\s*[^\n]*/)?.[0] ||
      titleMatch?.[1] ||
      '测验题').replace(/\*\*/g, '').trim();

  return ensureAgentQuestion({
    title,
    allow_skip: true,
    items: [
      {
        id: 'md_q1',
        type: 'quiz',
        prompt,
        options: opts.map((o) => ({ value: o.value, label: o.label })),
      },
    ],
  });
}

/** 任意正文 → 结构化反问（JSON 优先，其次 Markdown 选择题） */
export function recoverQuestionFromText(text: string): AgentQuestion | null {
  return extractAskUserFromText(text) ?? extractMarkdownQuiz(text);
}
