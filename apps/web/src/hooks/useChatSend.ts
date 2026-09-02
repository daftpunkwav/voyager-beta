import { useRef, useState } from 'react';
import { postChatMessage } from '@/bridge/chatSend';
import { fetchQuotaGuard, quotaWarnMessage } from '@/bridge/quotaGuard';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { useLlmAvailable } from './useLlmAvailable';

interface UseChatSendReturn {
  draft: string;
  setDraft: (v: string) => void;
  sending: boolean;
  llmMissing: boolean;
  send: () => Promise<void>;
}

/** Chat 页与悬浮窗共用的发送 hook。
 *
 * 负责 draft/sending/llmMissing/send;发送前过 token 日配额守卫(满则拒发并保留草稿);
 * 失败时还原草稿、追加系统气泡并清 thinking。
 * 输入框 DOM、placeholder、Enter 处理留在各视图,不抽万能 composer。
 */
export function useChatSend(): UseChatSendReturn {
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const llm = useLlmAvailable();
  const llmMissing = llm === 'missing';
  // ≥80% 配额提醒同一会话只弹一次,避免连发时刷屏;重挂载(换页/重开悬浮窗)即重置
  const quotaWarnedRef = useRef(false);

  const send = async () => {
    const content = draft.trim();
    if (!content || sending || llmMissing) return;
    // 先置 sending:守卫是异步查询,不先置位会在查询窗口内被重入双发
    setSending(true);
    try {
      // 发送前配额守卫(phase-67):满配额拒发并保留草稿;≥80% 提醒后照常发送
      const guard = await fetchQuotaGuard();
      if (guard.action === 'block') {
        useUIStore.getState().addToast({ type: 'error', message: guard.reason });
        return;
      }
      if (guard.action === 'warn' && !quotaWarnedRef.current) {
        quotaWarnedRef.current = true;
        useUIStore.getState().addToast({ type: 'warning', message: quotaWarnMessage(guard.ratio) });
      }
      setDraft('');
      const seq = await postChatMessage(content);
      useChatStore.getState().appendLocal({ seq, role: 'user', content });
    } catch (err) {
      setDraft(content);
      useChatStore.getState().appendLocal({
        seq: -Date.now(),
        role: 'system',
        content: err instanceof Error ? err.message : '发送失败:后端不可达',
      });
      useChatStore.setState({ thinking: false });
    } finally {
      setSending(false);
    }
  };

  return { draft, setDraft, sending, llmMissing, send };
}
