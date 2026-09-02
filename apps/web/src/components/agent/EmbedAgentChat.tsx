import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import type { ImportAssistContext } from '@/api/types';
import { sendUserTurn } from '@/bridge/chatSend';
import { useLlmAvailable } from '@/hooks/useLlmAvailable';
import { ChatLlmMissingTip } from '@/widgets/chat/ChatLlmMissingTip';
import { useUIStore } from '@/stores/uiStore';

export type EmbedChatMode = 'import' | 'graph';

interface ChatLine {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
}

interface EmbedAgentChatProps {
  mode: EmbedChatMode;
  title: string;
  subtitle?: string;
  agentInitial?: string;
  agentClassName?: string;
  importContext?: ImportAssistContext;
  graphNodeId?: string | null;
  placeholder?: string;
  /** 已废弃:助手不再自动勾选,保留 prop 仅为兼容宿主签名,不再调用。 */
  onSelectRepos?: (event: { repo_keys: string[]; action: 'set' | 'add' | 'remove'; reason?: string; count?: number }) => void;
  /** 已废弃:空 SSE stub 已删,无 key 时本组件自绘 ChatLlmMissingTip,不再通知宿主整块替换。 */
  onUnavailable?: () => void;
}

export function EmbedAgentChat({
  mode,
  title,
  subtitle,
  agentInitial = 'A',
  agentClassName = 'agent-orchestrator',
  importContext,
  graphNodeId,
  placeholder = '向助手描述你的需求…',
}: EmbedAgentChatProps) {
  const [lines, setLines] = useState<ChatLine[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content:
        mode === 'import'
          ? '我是 **导入助手**。可以问我「我 star 的项目都是什么类型」「推荐和已学项目类似的仓库」——我会结合 Stars / 已导入 / 学习进度回答。推荐结果请到左侧手动勾选。'
          : '我是 **Atlas · 图谱向导**，专门解读项目关系网络。可以问我「这两个项目为什么相连」。',
    },
  ]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const addToast = useUIStore((s) => s.addToast);
  const llm = useLlmAvailable();
  const llmMissing = llm === 'missing';

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [lines, sent]);

  const buildPrompt = (text: string): string => {
    if (mode === 'graph') {
      const node = graphNodeId || '未选';
      return `【图谱向导】当前节点：${node}。用户：${text}`;
    }
    const ctx = importContext ?? { mode: 'stars' as const };
    const available = (ctx.available_repo_keys ?? []).join('、') || '无';
    const selected = (ctx.selected_repo_keys ?? []).join('、') || '无';
    return `【导入助手】可选：${available}；已勾选：${selected}。用户：${text}。请建议勾选哪些,我在左侧手动勾选。`;
  };

  const send = async () => {
    const text = input.trim();
    if (!text || sending || llmMissing) return;
    setSending(true);
    const prompt = buildPrompt(text);
    try {
      // 发送成功后才落本地视图(phase-68 C):配额 block 抛错时输入保留、
      // 不插「已发到主对话」假阳性系统行
      await sendUserTurn(prompt);
      setInput('');
      setSent(true);
      setLines((prev) => [
        ...prev,
        { id: `u_${Date.now()}`, role: 'user', content: text },
        { id: `sys_${Date.now()}`, role: 'system', content: '已发到主对话，请打开悬浮窗查看。' },
      ]);
    } catch (err) {
      const message = err instanceof Error ? err.message : '发送失败';
      addToast({ type: 'error', message });
    } finally {
      setSending(false);
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  if (llmMissing) {
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
        </header>
        <div style={{ padding: 12 }}>
          <ChatLlmMissingTip />
        </div>
      </div>
    );
  }

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
      </header>
      <div className="embed-agent-chat__messages">
        {lines.map((l) => (
          <div key={l.id} className={`embed-msg embed-msg--${l.role}`}>
            {l.content}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <div className="embed-agent-chat__input">
        <textarea
          rows={2}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          disabled={sending}
          aria-label={`${title} 对话输入`}
        />
        <button
          type="button"
          className="embed-send-btn"
          onClick={() => void send()}
          disabled={sending || !input.trim()}
          aria-label="发送"
          title="发送 (Enter)"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" width={16} height={16}>
            <path d="M5 12h14M13 5l7 7-7 7" />
          </svg>
        </button>
      </div>
      <footer className="embed-agent-chat__footer">
        <span className="embed-agent-chat__hint">
          {mode === 'import' ? '推荐结果请左侧手动勾选' : '已改走主时间线'}
        </span>
      </footer>
    </div>
  );
}
