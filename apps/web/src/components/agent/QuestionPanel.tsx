import { useMemo, useState } from 'react';
import type {
  AgentQuestion,
  CheckboxQuestion,
  QuestionAnswer,
  QuestionItem,
  RadioQuestion,
  SliderQuestion,
} from '@/api/types';
import { isExamQuestion, questionTitle, stripOptionLetterPrefix, cleanQuestionText } from '@/utils/agentQuestion';

interface QuestionPanelProps {
  question: AgentQuestion;
  onSubmit: (answers: QuestionAnswer[]) => void;
  onSkip?: () => void;
}

function isAnswered(answer: QuestionAnswer | undefined): boolean {
  if (!answer) return false;
  switch (answer.type) {
    case 'radio':
      return Boolean(answer.value) && (answer.value !== '__other__' || Boolean(answer.other_text?.trim()));
    case 'checkbox':
      return Array.isArray(answer.values) && answer.values.length > 0;
    case 'slider':
      return typeof answer.value === 'number';
    case 'drag_sort':
      return Array.isArray(answer.order) && answer.order.length > 0;
    case 'knowledge_map':
      return Array.isArray(answer.checked) && answer.checked.length > 0;
    default:
      return false;
  }
}

export function QuestionPanel({ question, onSubmit, onSkip }: QuestionPanelProps) {
  const [answers, setAnswers] = useState<Record<string, QuestionAnswer>>({});
  const [invalidIds, setInvalidIds] = useState<Set<string>>(new Set());
  const exam = isExamQuestion(question);
  const title = questionTitle(question);
  const total = question.questions.length;

  const answeredCount = useMemo(
    () => question.questions.filter((q) => isAnswered(answers[q.id])).length,
    [question.questions, answers]
  );

  const handleChange = (id: string, answer: QuestionAnswer) => {
    setAnswers((prev) => ({ ...prev, [id]: { ...answer, question_id: id } }));
    if (isAnswered({ ...answer, question_id: id })) {
      setInvalidIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  const handleSubmit = () => {
    const missing = question.questions.filter((q) => !isAnswered(answers[q.id])).map((q) => q.id);
    if (missing.length > 0) {
      setInvalidIds(new Set(missing));
      return;
    }
    setInvalidIds(new Set());
    // 按题目顺序提交，带上 question_id（missing 已在上方校验，此处跳过空答案兜底类型）
    const ordered = question.questions
      .map((q) => {
        const a = answers[q.id];
        return a ? { ...a, question_id: q.id } : null;
      })
      .filter((x): x is NonNullable<typeof x> => x !== null);
    onSubmit(ordered);
  };

  return (
    <div
      className={`exam-panel ${exam ? 'exam-panel--quiz' : 'exam-panel--survey'}`}
      data-testid="question-panel"
    >
      <header className="exam-panel__header">
        <div className="exam-panel__title-row">
          <h3 className="exam-panel__title">{title}</h3>
          <span className="exam-panel__progress">
            {answeredCount}/{total}
          </span>
        </div>
        <div className="exam-panel__progress-bar" aria-hidden>
          <span style={{ width: `${total ? (answeredCount / total) * 100 : 0}%` }} />
        </div>
      </header>

      <div className="exam-panel__body">
        {question.questions.map((q, idx) => (
          <section
            key={q.id}
            className={`exam-q ${invalidIds.has(q.id) ? 'exam-q--invalid' : ''}`}
          >
            <div className="exam-q__index">
              {exam ? `第 ${idx + 1} 题` : `Q${idx + 1}`}
            </div>
            <h4 className="exam-q__prompt">{cleanQuestionText(q.text)}</h4>
            <QuestionItemRenderer
              item={q}
              answer={answers[q.id]}
              onChange={(a) => handleChange(q.id, a)}
            />
          </section>
        ))}
      </div>

      {invalidIds.size > 0 && (
        <p className="exam-panel__error">还有 {invalidIds.size} 题未作答</p>
      )}

      <footer className="exam-panel__footer">
        <button type="button" className="btn btn-primary" onClick={handleSubmit}>
          {exam ? '提交答案' : question.actions.submit.text}
        </button>
        {question.allow_skip && question.actions.skip && onSkip && (
          <button type="button" className="btn btn-ghost" onClick={onSkip}>
            {question.actions.skip.text}
          </button>
        )}
      </footer>
    </div>
  );
}

function QuestionItemRenderer({
  item,
  answer,
  onChange,
}: {
  item: QuestionItem;
  answer?: QuestionAnswer;
  onChange: (a: QuestionAnswer) => void;
}) {
  switch (item.type) {
    case 'radio':
      return <RadioBlock item={item} answer={answer} onChange={onChange} />;
    case 'checkbox':
      return <CheckboxBlock item={item} answer={answer} onChange={onChange} />;
    case 'slider':
      return <SliderBlock item={item} answer={answer} onChange={onChange} />;
    default:
      return (
        <p className="muted" style={{ fontSize: 12 }}>
          暂不支持的题型，请跳过或改用文字说明
        </p>
      );
  }
}

function RadioBlock({
  item,
  answer,
  onChange,
}: {
  item: RadioQuestion;
  answer?: QuestionAnswer;
  onChange: (a: QuestionAnswer) => void;
}) {
  const selected = answer?.type === 'radio' ? answer.value : '';
  const other = answer?.type === 'radio' ? answer.other_text ?? '' : '';
  const options = item.options.filter((o) =>
    (o.label || (o as { text?: string }).text || o.value || '').trim()
  );

  if (options.length === 0) {
    return (
      <div className="exam-options">
        <p className="exam-panel__error">选项未能加载，请在下方自由填写</p>
        <div className="exam-other">
          <input
            className="input"
            placeholder="直接填写你的回答…"
            value={other}
            onChange={(e) => {
              const v = e.target.value;
              onChange({
                type: 'radio',
                value: '__other__',
                other_text: v,
                question_id: item.id,
              });
            }}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="exam-options">
      {options.map((o, idx) => {
        const rawLabel = (o.label || (o as { text?: string }).text || o.value).trim();
        const label = stripOptionLetterPrefix(rawLabel);
        const active = selected === o.value;
        const letter = String.fromCharCode(65 + (idx % 26));
        return (
          <button
            key={o.value || label}
            type="button"
            className={`exam-option ${active ? 'is-active' : ''}`}
            onClick={() =>
              onChange({
                type: 'radio',
                value: o.value,
                other_text: other || undefined,
                question_id: item.id,
              })
            }
          >
            <span className="exam-option__mark" aria-hidden>
              {active ? '✓' : letter}
            </span>
            <span className="exam-option__text">
              <span className="exam-option__label">{label}</span>
              {o.description && <span className="exam-option__desc">{o.description}</span>}
            </span>
          </button>
        );
      })}
      {item.allow_other && (
        <div className="exam-other">
          <input
            className="input"
            placeholder="其他补充…"
            value={other}
            onChange={(e) => {
              const v = e.target.value;
              onChange({
                type: 'radio',
                value: v.trim() ? '__other__' : selected || '__other__',
                other_text: v,
                question_id: item.id,
              });
            }}
          />
        </div>
      )}
    </div>
  );
}

function CheckboxBlock({
  item,
  answer,
  onChange,
}: {
  item: CheckboxQuestion;
  answer?: QuestionAnswer;
  onChange: (a: QuestionAnswer) => void;
}) {
  const values = answer?.type === 'checkbox' ? answer.values : [];
  const options = item.options.filter((o) => (o.text || o.value || '').trim());

  const toggle = (v: string) => {
    const next = values.includes(v) ? values.filter((x) => x !== v) : [...values, v];
    onChange({ type: 'checkbox', values: next, question_id: item.id });
  };

  return (
    <div className="exam-options">
      {options.map((o, idx) => {
        const label = (o.text || o.value).trim();
        const active = values.includes(o.value);
        const letter = String.fromCharCode(65 + (idx % 26));
        return (
          <button
            key={o.value || label}
            type="button"
            className={`exam-option ${active ? 'is-active' : ''}`}
            onClick={() => toggle(o.value)}
          >
            <span className="exam-option__mark" aria-hidden>
              {active ? '✓' : letter}
            </span>
            <span className="exam-option__label">{label}</span>
          </button>
        );
      })}
    </div>
  );
}

function SliderBlock({
  item,
  answer,
  onChange,
}: {
  item: SliderQuestion;
  answer?: QuestionAnswer;
  onChange: (a: QuestionAnswer) => void;
}) {
  const mid = Math.floor((item.min + item.max) / 2);
  const value = answer?.type === 'slider' ? answer.value : mid;
  return (
    <div className="exam-slider">
      <input
        type="range"
        min={item.min}
        max={item.max}
        value={value}
        onChange={(e) =>
          onChange({
            type: 'slider',
            value: Number(e.target.value),
            question_id: item.id,
          })
        }
      />
      <div className="exam-slider__meta">
        <span>{item.labels?.[String(item.min)] ?? item.min}</span>
        <strong>{item.labels?.[String(value)] ?? value}</strong>
        <span>{item.labels?.[String(item.max)] ?? item.max}</span>
      </div>
    </div>
  );
}
