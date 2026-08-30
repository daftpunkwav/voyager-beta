/** agent.ask 弹窗:四种题型(text/choice/slider/confirm),提交经 answer_question 回投。
 *
 * 供 Chat 页与常驻悬浮窗共用(§10.12)，放在 widgets 层避免页面私有组件被反向依赖。
 */

import { useEffect, useState } from 'react';
import { callCapability, ServiceError } from '@/bridge/client';
import { useChatStore } from '@/stores/chatStore';

/** 前端兜底超时:后端 Question 默认 120s(见 agent/tools/ask_user.py),到点 Future 已丢弃;
 * 前端略放宽 10s 后关弹窗,避免 UI 卡在永远不会被回投命中的问题上。 */
const ANSWER_WINDOW_MS = 130_000;

export function AskDialog() {
  const question = useChatStore((s) => s.question);
  const clearQuestion = useChatStore((s) => s.clearQuestion);
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // 超时兜底:answer_question 的 Future 只在 ask 等待期间存在,超时后回投必 miss
  const questionId = question?.questionId;
  useEffect(() => {
    if (!questionId) return;
    const timer = setTimeout(() => {
      useChatStore.getState().addSystem('问题超时未答,已关闭弹窗;agent 将按默认继续。');
      useChatStore.getState().clearQuestion();
    }, ANSWER_WINDOW_MS);
    return () => clearTimeout(timer);
  }, [questionId]);

  if (!question) return null;

  const submit = async (raw: unknown) => {
    setBusy(true);
    setError(null);
    try {
      const out = await callCapability<{ matched: boolean }>('agent', 'answer_question', {
        question_id: question.questionId,
        value: raw,
      });
      if (out.matched === false) {
        // 后端已无此问题(超时被丢弃):提示后照常收起,让用户继续对话
        useChatStore.getState().addSystem('该问题已失效(可能已超时),无需再答。');
      }
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
      <div className="ask-dialog glass-card glass-card--dialog">
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
