/** 消息流渲染:user/agent 气泡(Markdown+高亮)、系统提示、任务进度卡、思考态。
 *
 * 供 Chat 页与常驻悬浮窗共用(§10.12)，放在 widgets 层避免页面私有组件被反向依赖。
 */

import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { type ChatMessage, useChatStore } from '@/stores/chatStore';

/**
 * Markdown 安全性:react-markdown 未启用 rehype-raw,原始 HTML 一律转义为文本
 * (无注入面);消毒依赖留待未来引入 raw html 能力时启用。
 */
export function MessageList() {
  const messages = useChatStore((s) => s.messages);
  const thinking = useChatStore((s) => s.thinking);
  const artifacts = useChatStore((s) => s.artifacts);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages.length, thinking, artifacts.length]);

  return (
    <div className="chat-stream">
      {messages.map((m) => (
        <Bubble key={`${m.seq}-${m.role}`} msg={m} />
      ))}
      {artifacts.map((a) => (
        <Link key={a.seq} to={`/notes?open=${a.noteId}`} className="note-artifact">
          <span className="note-artifact__icon" aria-hidden>
            ▤
          </span>
          <span>已创建笔记:{a.title}</span>
          <span className="small muted">查看 →</span>
        </Link>
      ))}
      {thinking ? (
        <div className="chat-bubble chat-bubble--agent chat-typing" aria-label="正在处理">
          <span />
          <span />
          <span />
        </div>
      ) : null}
      <div ref={bottomRef} />
    </div>
  );
}

function Bubble({ msg }: { msg: ChatMessage }) {
  if (msg.role === 'system') {
    return <div className="chat-system">{msg.content}</div>;
  }
  const cls =
    msg.role === 'user' ? 'chat-bubble chat-bubble--user' : 'chat-bubble chat-bubble--agent';
  return (
    <div className={cls}>
      {msg.proactive ? <span className="chat-proactive-tag">主动</span> : null}
      <div className="chat-md">
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
          {msg.content}
        </ReactMarkdown>
      </div>
    </div>
  );
}

/** 任务进度卡区域(渲染在输入框上方,含 completed/failed 收尾态)。 */
export function TaskCards() {
  const cards = useChatStore((s) => s.cards);
  const order = useChatStore((s) => s.cardOrder);
  const visible = order
    .map((k) => cards[k])
    .filter((c): c is NonNullable<typeof c> => Boolean(c));
  if (visible.length === 0) return null;
  return (
    <div className="chat-cards">
      {visible.map((c) => (
        <div key={c.key} className={`chat-card chat-card--${c.status}`}>
          <div className="chat-card__head">
            <span className="chat-card__label">{c.label}</span>
            <span className="chat-card__stage small muted">
              {c.status === 'failed' ? `失败:${c.error ?? ''}` : c.stage}
            </span>
          </div>
          <div className="chat-card__bar">
            <div className="chat-card__fill" style={{ width: `${Math.round(c.progress * 100)}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}
