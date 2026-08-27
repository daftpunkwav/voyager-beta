import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { getApi } from '@/api/client';
import type { ImportAssistContext, SelectReposEvent, SSEEvent } from '@/api/types';
import { ApiRequestError } from '@/api/client';
import { consumeAgentSSEStream } from '@/utils/agentSSEStream';
import { formatErrorToast } from '@/utils/errorCodes';
import { StreamRenderer } from '@/components/agent/StreamRenderer';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
import { useUIStore } from '@/stores/uiStore';

export type EmbedChatMode = 'import' | 'graph';

interface ChatLine {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  thinking?: string;
}

const AGENT_DOWN_CODES = new Set([
  'AGENT_MODULE_DOWN',
  'AGENT_LLM_UNAVAILABLE',
  'MODULE_LOAD_FAILED',
  'AGENT_IMPORT_ASSIST_FAILED',
]);

interface EmbedAgentChatProps {
  mode: EmbedChatMode;
  title: string;
  subtitle?: string;
  agentInitial?: string;
  agentClassName?: string;
  importContext?: ImportAssistContext;
  graphNodeId?: string | null;
  placeholder?: string;
  onSelectRepos?: (event: SelectReposEvent) => void;
  /** Agent 不可用时通知父组件隐藏面板 */
  onUnavailable?: () => void;
}

export function EmbedAgentChat({
  mode,
  title,
  subtitle,
  agentInitial = 'A',
  agentClassName = 'agent-hub',
  importContext,
  graphNodeId,
  placeholder = '向助手描述你的需求…',
  onSelectRepos,
  onUnavailable,
}: EmbedAgentChatProps) {
  const [lines, setLines] = useState<ChatLine[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content:
        mode === 'import'
          ? '我是 **导入助手**。可以说「我 star 的项目都是什么类型」「推荐和已学项目类似的仓库」——我会结合 **Stars / 已导入 / 学习进度** 回答，并在左侧自动勾选。确认后点「导入选中」。'
          : '我是 **Atlas · 图谱向导**，专门解读项目关系网络。可以问我「这两个项目为什么相连」。',
    },
  ]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState('');
  const [streamThinking, setStreamThinking] = useState('');
  const [tokenHint, setTokenHint] = useState({ in: 0, out: 0 });
  const [error, setError] = useState<string | null>(null);
  const [lastAction, setLastAction] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const streamAbortRef = useRef<AbortController | null>(null);
  const textAccRef = useRef('');
  const thinkingAccRef = useRef('');
  const addToast = useUIStore((s) => s.addToast);
  const importContextRef = useRef(importContext);
  importContextRef.current = importContext;

  const markUnavailable = (code: string) => {
    if (!AGENT_DOWN_CODES.has(code)) return;
    setUnavailable(true);
    onUnavailable?.();
    addToast({
      type: 'error',
      code,
      message: formatErrorToast(code, 'Agent 助手不可用，已切换手动模式'),
      duration: 5000,
    });
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [lines, streaming, streamText, streamThinking, error, lastAction]);

  useEffect(
    () => () => {
      streamAbortRef.current?.abort();
    },
    [],
  );

  // 挂载时探测 /health，agent 未加载则立即降级
  useEffect(() => {
    let cancelled = false;
    const probe = async () => {
      try {
        const base = import.meta.env.VITE_API_BASE_URL ?? '';
        const res = await fetch(`${base}/health`);
        if (!res.ok || cancelled) return;
        const body = (await res.json()) as {
          modules?: Array<{ name: string; loaded: boolean }>;
        };
        const agent = body.modules?.find((m) => m.name === 'agent');
        if (agent && !agent.loaded && !cancelled) {
          markUnavailable('AGENT_MODULE_DOWN');
        }
      } catch {
        /* 健康检查失败不阻塞，等首次发送再降级 */
      }
    };
    void probe();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 仅挂载探测一次
  }, []);

  const abortStream = () => {
    streamAbortRef.current?.abort();
    streamAbortRef.current = null;
    setStreaming(false);
    setStreamText('');
    setStreamThinking('');
  };

  const applySelectRepos = (raw: Record<string, unknown>) => {
    const event: SelectReposEvent = {
      repo_keys: Array.isArray(raw.repo_keys)
        ? (raw.repo_keys as unknown[]).map(String)
        : [],
      action: (raw.action as SelectReposEvent['action']) || 'set',
      reason: typeof raw.reason === 'string' ? raw.reason : undefined,
      count: typeof raw.count === 'number' ? raw.count : undefined,
    };
    onSelectRepos?.(event);
    const n = event.repo_keys.length;
    const label =
      event.action === 'remove'
        ? `已取消勾选 ${n} 个仓库`
        : event.action === 'add'
          ? `已追加勾选 ${n} 个仓库`
          : `已自动勾选 ${n} 个仓库`;
    setLastAction(label);
    setLines((prev) => [
      ...prev,
      {
        id: `sys_${Date.now()}`,
        role: 'system',
        content: `⚙️ **系统操控** · ${label}。请看左侧勾选，确认后点 **导入选中**。`,
      },
    ]);
  };

  const send = async () => {
    const text = input.trim();
    if (!text || streaming || unavailable) return;
    setInput('');
    setError(null);
    setLastAction(null);
    textAccRef.current = '';
    thinkingAccRef.current = '';
    setStreamText('');
    setStreamThinking('');
    setLines((prev) => [...prev, { id: `u_${Date.now()}`, role: 'user', content: text }]);
    setStreaming(true);
    streamAbortRef.current?.abort();
    const ac = new AbortController();
    streamAbortRef.current = ac;

    const api = getApi();
    const ctx = importContextRef.current ?? { mode: 'stars' as const };
    const stream =
      mode === 'import'
        ? api.importAssistChat(text, ctx, ac.signal)
        : api.graphGuideChat(text, { selected_node_id: graphNodeId }, ac.signal);

    let flushTimer: ReturnType<typeof setTimeout> | null = null;
    const clearFlush = () => {
      if (flushTimer) {
        clearTimeout(flushTimer);
        flushTimer = null;
      }
    };
    const scheduleUi = () => {
      if (flushTimer) return;
      flushTimer = setTimeout(() => {
        flushTimer = null;
        if (ac.signal.aborted) return;
        setStreamText(textAccRef.current);
        setStreamThinking(thinkingAccRef.current);
      }, 16);
    };

    try {
      const result = await consumeAgentSSEStream(
        stream as AsyncGenerator<SSEEvent>,
        {
          onTextDelta: (_p, full) => {
            textAccRef.current = full;
            scheduleUi();
          },
          onThinking: (_p, full) => {
            thinkingAccRef.current = full;
            scheduleUi();
          },
          onSelectRepos: applySelectRepos,
          onDone: (data) => {
            const usage = data as { usage?: { tokens?: number } };
            setTokenHint((t) => ({
              in: t.in + Math.round(text.length / 4),
              out:
                t.out +
                (usage.usage?.tokens ?? Math.round(textAccRef.current.length / 4)),
            }));
          },
          onError: (msg) => setError(msg),
        },
        { signal: ac.signal },
      );

      clearFlush();
      const assistant = result.text;
      const thinking = result.thinking;
      setStreamText('');
      setStreamThinking('');

      setLines((prev) => {
        if (!assistant.trim()) {
          if (!result.sawError) {
            return [
              ...prev,
              {
                id: `a_${Date.now()}`,
                role: 'assistant',
                content:
                  '我这边暂时没生成正文。请再说一次需求（例如「推荐 Python Web 项目」或「我 star 了哪些类型」）。',
                thinking: thinking || undefined,
              },
            ];
          }
          return prev;
        }
        return [
          ...prev,
          {
            id: `a_${Date.now()}`,
            role: 'assistant',
            content: assistant,
            thinking: thinking || undefined,
          },
        ];
      });

      if (result.sawError) {
        const code = result.errorCode || 'AGENT_CHAT_FAILED';
        addToast({
          type: 'error',
          code,
          message: formatErrorToast(code, result.errorMessage || '助手返回错误'),
        });
        markUnavailable(code);
      }
    } catch (err) {
      clearFlush();
      if (ac.signal.aborted) return;
      if (err instanceof ApiRequestError) {
        setError(err.message);
        addToast({
          type: 'error',
          code: err.code,
          message: formatErrorToast(err.code, err.message),
        });
        markUnavailable(err.code);
      } else {
        const message = err instanceof Error ? err.message : '连接中断，请重试';
        setError(message);
        addToast({ type: 'error', message });
      }
    } finally {
      clearFlush();
      if (streamAbortRef.current === ac) {
        streamAbortRef.current = null;
      }
      setStreaming(false);
      setStreamText('');
      setStreamThinking('');
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void send();
      return;
    }
    if (e.key === 'Escape' && streaming) {
      e.preventDefault();
      abortStream();
    }
  };

  if (unavailable) return null;

  return (
    <div className="embed-agent-chat">
      <header className="embed-agent-chat__head">
        <div className={`agent-avatar ${agentClassName} active`}>
          <span>{agentInitial}</span>
        </div>
        <div>
          <div className="embed-agent-chat__title">{title}</div>
          {subtitle && <div className="embed-agent-chat__sub">{subtitle}</div>}
        </div>
        {lastAction && (
          <span className="embed-agent-chat__action-pill" title={lastAction}>
            操控中
          </span>
        )}
      </header>
      <div className="embed-agent-chat__messages">
        {error && (
          <div className="embed-msg embed-msg--error" role="alert" data-testid="embed-chat-error">
            {error}
          </div>
        )}
        {lines.map((l) => (
          <div key={l.id} className={`embed-msg embed-msg--${l.role}`}>
            {l.role === 'user' ? (
              l.content
            ) : l.role === 'assistant' ? (
              <StreamRenderer content={l.content} thinking={l.thinking} streaming={false} />
            ) : (
              <MarkdownRenderer content={l.content} />
            )}
          </div>
        ))}
        {streaming && (
          <div className="embed-msg embed-msg--assistant embed-msg--streaming">
            {streamText || streamThinking ? (
              <StreamRenderer
                content={streamText}
                thinking={streamThinking || undefined}
                streaming
              />
            ) : (
              <span className="embed-msg--typing">助手思考中…</span>
            )}
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="embed-agent-chat__input">
        <textarea
          rows={2}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          disabled={streaming}
          aria-label={`${title} 对话输入`}
        />
        <button
          type="button"
          className="embed-send-btn"
          onClick={() => void send()}
          disabled={streaming || !input.trim()}
          aria-label="发送"
          title="发送 (Enter)"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" width={16} height={16}>
            <path d="M5 12h14M13 5l7 7-7 7" />
          </svg>
        </button>
      </div>
      <footer className="embed-agent-chat__footer">
        <span className="mono">
          in {Math.round(tokenHint.in)} · out {Math.round(tokenHint.out)} tok
        </span>
        {mode === 'import' && (
          <span className="embed-agent-chat__hint">可操控左侧勾选</span>
        )}
      </footer>
    </div>
  );
}
