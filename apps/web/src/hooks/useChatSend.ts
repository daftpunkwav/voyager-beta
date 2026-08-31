import { useState } from 'react';
import { postChatMessage } from '@/bridge/chatSend';
import { useChatStore } from '@/stores/chatStore';
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
 * 负责 draft/sending/llmMissing/send;失败时还原草稿、追加系统气泡并清 thinking。
 * 输入框 DOM、placeholder、Enter 处理留在各视图,不抽万能 composer。
 */
export function useChatSend(): UseChatSendReturn {
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const llm = useLlmAvailable();
  const llmMissing = llm === 'missing';

  const send = async () => {
    const content = draft.trim();
    if (!content || sending || llmMissing) return;
    setSending(true);
    setDraft('');
    try {
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
