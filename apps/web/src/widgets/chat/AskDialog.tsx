/** agent.ask 弹窗:四种题型(text/choice/slider/confirm),提交经 answer_question 回投。
 *
 * 供 Chat 页与常驻悬浮窗共用(§10.12)，放在 widgets 层避免页面私有组件被反向依赖。
 */

import { useState } from 'react';
import { callCapability, ServiceError } from '@/bridge/client';
import { useChatStore } from '@/bridge/chatStore';

export function AskDialog() {
  const question = useChatStore((s) => s.question);
  const clearQuestion = useChatStore((s) => s.clearQuestion);
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!question) return null;

  const submit = async (raw: unknown) => {
    setBusy(true);
    setError(null);
    try {
      await callCapability('agent', 'answer_question', {
        question_id: question.questionId,
        value: raw,
      });
      clearQuestion();
      setValue('');
    } catch (err) {
      setError((err as ServiceError).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="ask-mask" role="dialog" aria-modal="true" aria-label={question.prompt}>
      <div className="ask-dialog">
        <div className="ask-dialog__prompt">{question.prompt}</div>

        {question.kind === 'text' ? (
          <>
            <input
              className="setting-input"
              value={value}
              autoFocus
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && value.trim()) void submit(value.trim());
              }}
            />
            <div className="ask-actions">
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy || !value.trim()}
                onClick={() => void submit(value.trim())}
              >
                回答
              </button>
            </div>
          </>
        ) : null}

        {question.kind === 'choice' ? (
          <div className="ask-options">
            {question.options.map((opt) => (
              <button
                type="button"
                key={opt}
                className="ask-option"
                disabled={busy}
                onClick={() => void submit(opt)}
              >
                {opt}
              </button>
            ))}
          </div>
        ) : null}

        {question.kind === 'slider' ? (
          <SliderAsk min={question.min} max={question.max} busy={busy} onSubmit={submit} />
        ) : null}

        {question.kind === 'confirm' ? (
          <div className="ask-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={() => void submit(true)}
            >
              确认
            </button>
            <button type="button" className="btn" disabled={busy} onClick={() => void submit(false)}>
              取消
            </button>
          </div>
        ) : null}

        {error ? <div className="setting-field__error small">{error}</div> : null}
      </div>
    </div>
  );
}

function SliderAsk({
  min,
  max,
  busy,
  onSubmit,
}: {
  min: number | null;
  max: number | null;
  busy: boolean;
  onSubmit: (v: number) => Promise<void>;
}) {
  const lo = min ?? 0;
  const hi = max ?? 100;
  const [v, setV] = useState(Math.round((lo + hi) / 2));
  return (
    <>
      <div className="small muted mono" style={{ textAlign: 'center' }}>
        {v}
      </div>
      <input
        type="range"
        min={lo}
        max={hi}
        value={v}
        disabled={busy}
        style={{ width: '100%' }}
        onChange={(e) => setV(Number(e.target.value))}
      />
      <div className="ask-actions">
        <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void onSubmit(v)}>
          回答
        </button>
      </div>
    </>
  );
}
