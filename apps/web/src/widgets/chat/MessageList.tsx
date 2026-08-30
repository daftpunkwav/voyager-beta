/** 消息流渲染:user/agent 气泡(Markdown+高亮)、系统提示、任务进度卡、思考态。
 *
 * 供 Chat 页与常驻悬浮窗共用(§10.12)，放在 widgets 层避免页面私有组件被反向依赖。
 */

import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import type { Options as SanitizeOptions } from 'rehype-sanitize';
import {
  type ChatMessage,
  type NoteArtifact,
  useChatStore,
} from '@/stores/chatStore';
import { callCapability, ServiceError } from '@/bridge/client';
import { routes } from '@/utils/routes';
import { safeHttpUrl, safeInternalPath } from '@/utils/safeUrl';

/** 允许 highlight.js 注入的 class,与 MarkdownRenderer 同一防线(纵深防御) */
const sanitizeSchema: SanitizeOptions = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    code: [...(defaultSchema.attributes?.code ?? []), ['className']],
    span: [...(defaultSchema.attributes?.span ?? []), ['className']],
    pre: [...(defaultSchema.attributes?.pre ?? []), ['className']],
  },
};

const mdComponents: Components = {
  a({ href, children }) {
    const internal = safeInternalPath(href);
    if (internal) return <a href={internal}>{children}</a>;
    const http = safeHttpUrl(href);
    if (http) {
      return (
        <a href={http} target="_blank" rel="noopener noreferrer">
          {children}
        </a>
      );
    }
    return <span>{children}</span>;
  },
};

export function MessageList() {
  const messages = useChatStore((s) => s.messages);
  const thinking = useChatStore((s) => s.thinking);
  const artifacts = useChatStore((s) => s.artifacts);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const reduce =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    bottomRef.current?.scrollIntoView({
      behavior: reduce ? 'auto' : 'smooth',
      block: 'end',
    });
  }, [messages.length, thinking, artifacts.length]);

  return (
    <div className="chat-stream">
      {messages.map((m) => (
        <Bubble key={`${m.seq}-${m.role}`} msg={m} />
      ))}
      {artifacts.map((a) => (
        <NoteArtifactCard key={a.seq} artifact={a} />
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

/** 对话内 Markdown 渲染(GFM + 高亮 + 白名单 sanitize),气泡与产物预览共用同一防线。 */
function ChatMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeHighlight, [rehypeSanitize, sanitizeSchema]]}
      components={mdComponents}
    >
      {content}
    </ReactMarkdown>
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
        <ChatMarkdown content={msg.content} />
      </div>
      {msg.proactive && msg.reason ? (
        // 主动出处(§9.8/§10.2):触发源短句,内容排版不算 Chrome
        <div className="chat-origin small muted" aria-label={`为什么找我:${msg.reason}`}>
          为什么找我:{msg.reason}
        </div>
      ) : null}
    </div>
  );
}

/** 产物卡(§10.2 快速预览的笔记部分):默认摘要行,点击就地展开 Markdown 预览,再点收起;
 *  跳笔记页的入口保留在行尾。PPT/Word 产物本阶段不做:office 未挂进聚合后端,无处预览。 */
function NoteArtifactCard({ artifact }: { artifact: NoteArtifact }) {
  const [open, setOpen] = useState(false);
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const toggle = async () => {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    // 全文只取一次:收起再展开不重复请求,失败结果也记住(避免反复打已删笔记)
    if (content !== null || error !== null || loading) return;
    setLoading(true);
    try {
      const row = await callCapability<{ content?: string }>(
        'notes',
        'get_note',
        { note_id: artifact.noteId },
      );
      setContent(String(row.content ?? ''));
    } catch (err) {
      // NOT_FOUND = 笔记已删除/清空,给用户能读懂的说明,不透出裸 uuid 错误
      const code = err instanceof ServiceError ? err.code : '';
      setError(
        code.endsWith('NOT_FOUND')
          ? '笔记不存在或已被删除'
          : err instanceof Error
            ? err.message
            : '笔记加载失败',
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="note-artifact">
      <button
        type="button"
        className="note-artifact__main"
        aria-expanded={open}
        onClick={() => void toggle()}
      >
        <span className="note-artifact__icon" aria-hidden>
          ▤
        </span>
        <span className="note-artifact__title">已创建笔记:{artifact.title}</span>
        <span className="small muted">{open ? '收起 ▴' : '展开 ▾'}</span>
      </button>
      <Link to={routes.note(artifact.noteId)} className="note-artifact__open small">
        笔记页 →
      </Link>
      {open ? (
        <div className="note-artifact__preview chat-md">
          {loading ? <span className="small muted">加载中…</span> : null}
          {!loading && error ? <span className="small">⚠ {error}</span> : null}
          {!loading && !error && content !== null ? (
            content ? (
              <ChatMarkdown content={content} />
            ) : (
              <span className="small muted">(空笔记)</span>
            )
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** 实时工具步骤(phase-06):输入区上方一行「正在:{name}」,新步骤覆盖旧的;
 *  agent.message / 回合结束由 chatStore 清掉。不做完整 trajectory 面板(§9.2)。 */
export function StepLine() {
  const current = useChatStore((s) => s.currentStep);
  if (!current?.name) return null;
  const who = current.subagent ? `${current.subagent} · ` : '';
  return (
    <div className="chat-step small muted" role="status">
      {who}正在:{current.name}
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
      {visible.map((c) => {
        const cls = `chat-card chat-card--${c.status}`;
        const body = (
          <>
            <div className="chat-card__head">
              {/* label 被 project/kind 占用时悬停可见完整 id */}
              <span className="chat-card__label" title={c.key}>
                {c.label}
              </span>
              <span className="chat-card__stage small muted">
                {c.status === 'failed' ? `失败:${c.error ?? '原因未提供'}` : c.stage}
              </span>
            </div>
            <div className="chat-card__bar">
              <div
                className="chat-card__fill"
                style={{ width: `${Math.round(c.progress * 100)}%` }}
              />
            </div>
          </>
        );
        // 有资源详情页的卡整卡可点进资源页;graph 的 job_id 无详情页,保持纯展示
        return c.link ? (
          <Link key={c.key} to={c.link} className={`${cls} chat-card--link`}>
            {body}
          </Link>
        ) : (
          <div key={c.key} className={cls}>
            {body}
          </div>
        );
      })}
    </div>
  );
}
