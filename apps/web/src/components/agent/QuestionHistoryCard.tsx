import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import type {
  AgentMessage,
  AgentQuestion,
  QuestionAnswer,
  QuestionAnswerRecord,
  QuestionItem,
} from '@/api/types';
import {
  cleanQuestionText,
  formatRadioOptionLabel,
  isExamQuestion,
  questionTitle,
  stripOptionLetterPrefix,
} from '@/utils/agentQuestion';
import { QuestionPanel } from './QuestionPanel';

/** 挂到 body 的玻璃弹层，避免被聊天列 / 窄侧栏裁切成竖条 */
function QuestionModalShell({
  open,
  onClose,
  children,
  testId,
  closeOnBackdrop = true,
  modalClassName,
}: {
  open: boolean;
  onClose?: () => void;
  children: ReactNode;
  testId?: string;
  closeOnBackdrop?: boolean;
  modalClassName?: string;
}) {
  const handleClose = useCallback(() => {
    onClose?.();
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && closeOnBackdrop) handleClose();
    };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open, handleClose, closeOnBackdrop]);

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <div
      className="question-modal-backdrop"
      onClick={closeOnBackdrop ? handleClose : undefined}
      role="presentation"
      data-testid={testId}
    >
      <div
        className={['question-modal', 'glass-card', 'glass-card--dialog', modalClassName].filter(Boolean).join(' ')}
        role="dialog"
        aria-modal
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>,
    document.body
  );
}

function findAnswer(
  answers: QuestionAnswer[] | undefined,
  item: QuestionItem,
  index: number
): QuestionAnswer | undefined {
  if (!answers?.length) return undefined;
  return answers.find((a) => a.question_id === item.id) ?? answers[index];
}

function isOptionSelected(answer: QuestionAnswer | undefined, value: string): boolean {
  if (!answer) return false;
  if (answer.type === 'radio') return answer.value === value;
  if (answer.type === 'checkbox') return answer.values.includes(value);
  return false;
}

/** 测验/反问详情：只展示题目 + 全部选项 */
function QuestionDetailList({ question }: { question: AgentQuestion }) {
  return (
    <ul className="qa-detail-list">
      {question.questions.map((q, i) => (
        <li key={q.id} className="qa-detail-item">
          <strong className="qa-detail-item__q">
            {i + 1}. {cleanQuestionText(q.text)}
          </strong>
          {q.type === 'radio' && (
            <div className="qa-detail-opts">
              {q.options.map((o, oi) => (
                <span key={o.value || `${oi}`} className="qa-detail-opt">
                  {formatRadioOptionLabel(o, oi)}
                </span>
              ))}
            </div>
          )}
          {q.type === 'checkbox' && (
            <div className="qa-detail-opts">
              {q.options.map((o) => (
                <span key={o.value} className="qa-detail-opt">
                  {stripOptionLetterPrefix(o.text)}
                </span>
              ))}
            </div>
          )}
          {q.type === 'slider' && (
            <p className="qa-detail-item__meta">
              量表 {q.min} – {q.max}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}

/** 回答详情：题目 + 全部选项，并标注用户选择 */
function AnswerDetailList({ record }: { record: QuestionAnswerRecord }) {
  const q = record.question;
  const hasStructured = q?.questions?.some(
    (item) =>
      (item.type === 'radio' && item.options.length > 0) ||
      (item.type === 'checkbox' && item.options.length > 0) ||
      item.type === 'slider'
  );

  if (!hasStructured) {
    return (
      <ul className="qa-detail-list">
        {record.details.map((d, i) => (
          <li key={`${d.question}-${i}`} className="qa-detail-item">
            <strong className="qa-detail-item__q">
              {i + 1}. {cleanQuestionText(d.question)}
            </strong>
            <p className="qa-detail-item__a">{record.skipped ? '（跳过）' : d.answer}</p>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <ul className="qa-detail-list">
      {q.questions.map((item, i) => {
        const answer = findAnswer(record.answers, item, i);
        return (
          <li key={item.id} className="qa-detail-item">
            <strong className="qa-detail-item__q">
              {i + 1}. {cleanQuestionText(item.text)}
            </strong>
            {record.skipped ? (
              <p className="qa-detail-item__a">（跳过）</p>
            ) : (
              <>
                {item.type === 'radio' && (
                  <div className="qa-detail-opts">
                    {item.options.map((o, oi) => {
                      const selected = isOptionSelected(answer, o.value);
                      return (
                        <span
                          key={o.value || `${oi}`}
                          className={`qa-detail-opt${selected ? ' is-selected' : ''}`}
                        >
                          <span className="qa-detail-opt__label">
                            {formatRadioOptionLabel(o, oi)}
                          </span>
                          {selected && <span className="qa-detail-opt__tag">你的选择</span>}
                        </span>
                      );
                    })}
                  </div>
                )}
                {item.type === 'checkbox' && (
                  <div className="qa-detail-opts">
                    {item.options.map((o) => {
                      const selected = isOptionSelected(answer, o.value);
                      return (
                        <span
                          key={o.value}
                          className={`qa-detail-opt${selected ? ' is-selected' : ''}`}
                        >
                          <span className="qa-detail-opt__label">
                            {stripOptionLetterPrefix(o.text)}
                          </span>
                          {selected && <span className="qa-detail-opt__tag">已选</span>}
                        </span>
                      );
                    })}
                  </div>
                )}
                {item.type === 'slider' && answer?.type === 'slider' && (
                  <p className="qa-detail-item__a">作答：{answer.value}</p>
                )}
                {item.type === 'radio' &&
                  answer?.type === 'radio' &&
                  answer.value === '__other__' &&
                  answer.other_text && (
                    <p className="qa-detail-item__a">其他：{answer.other_text}</p>
                  )}
              </>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** 对话历史中的反问卡片：玻璃票卡摘要 + 点击展开详情 */
export function QuestionOfferCard({
  question,
  agentName,
}: {
  question: AgentQuestion;
  agentName?: string;
}) {
  const [open, setOpen] = useState(false);
  const title = questionTitle(question);
  const n = question.questions.length;
  const exam = isExamQuestion(question);

  return (
    <>
      <button type="button" className="qa-card qa-card--offer" onClick={() => setOpen(true)}>
        <span className="qa-card__badge">{exam ? '测验' : '反问'}</span>
        <span className="qa-card__title">{title}</span>
        <span className="qa-card__meta">
          {n} 题 · {agentName ?? 'Agent'} · 点开查看
        </span>
      </button>
      <QuestionModalShell open={open} onClose={() => setOpen(false)}>
        <div className="question-modal__head">
          <span className="question-modal__badge">{exam ? '测验详情' : '反问详情'}</span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>
            关闭
          </button>
        </div>
        <QuestionDetailList question={question} />
      </QuestionModalShell>
    </>
  );
}

/** 用户答题结果卡片 */
export function QuestionAnswerCard({ record }: { record: QuestionAnswerRecord }) {
  const [open, setOpen] = useState(false);
  const title = questionTitle(record.question);
  const previewLines = record.skipped
    ? []
    : (record.details ?? [])
        .filter((d) => d.answer && d.answer !== '（未答）')
        .slice(0, 3);

  return (
    <>
      <button type="button" className="qa-card qa-card--answer" onClick={() => setOpen(true)}>
        <span className="qa-card__badge">{record.skipped ? '已跳过' : '已回答'}</span>
        <span className="qa-card__title">{title}</span>
        {record.skipped ? (
          <span className="qa-card__meta">点击查看题目</span>
        ) : previewLines.length > 0 ? (
          <span className="qa-card__meta qa-card__meta--answers">
            {previewLines.map((d, i) => (
              <span key={`${d.question}-${i}`} className="qa-card__answer-line">
                {d.answer}
              </span>
            ))}
            {(record.details?.length ?? 0) > previewLines.length && (
              <span className="qa-card__answer-more">
                另有 {(record.details?.length ?? 0) - previewLines.length} 题 · 点开查看
              </span>
            )}
          </span>
        ) : (
          <span className="qa-card__meta">{record.summary || '点开查看'}</span>
        )}
      </button>
      <QuestionModalShell open={open} onClose={() => setOpen(false)}>
        <div className="question-modal__head">
          <span className="question-modal__badge">回答详情</span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>
            关闭
          </button>
        </div>
        <AnswerDetailList record={record} />
      </QuestionModalShell>
    </>
  );
}

/** 从消息内容恢复历史反问/回答展示 */
export function hydrateMessageVisual(message: AgentMessage): AgentMessage {
  if (message.question || message.question_answer) return message;
  return message;
}

/** 活动弹窗包装（进行中的反问，不可点遮罩关闭） */
export function LiveQuestionModal({
  question,
  agentLabel,
  onSubmit,
  onSkip,
}: {
  question: AgentQuestion;
  agentLabel: string;
  onSubmit: Parameters<typeof QuestionPanel>[0]['onSubmit'];
  onSkip?: () => void;
}) {
  const exam = isExamQuestion(question);

  return (
    <QuestionModalShell
      open
      closeOnBackdrop={false}
      testId="question-modal"
      modalClassName="question-modal--live"
    >
      <div className="question-modal__head">
        <span className="question-modal__badge">{exam ? '测验' : '请回答'}</span>
        <span className="question-modal__agent">{agentLabel}</span>
      </div>
      <QuestionPanel question={question} onSubmit={onSubmit} onSkip={onSkip} />
    </QuestionModalShell>
  );
}
