/** 对话页感知:只报消息条数。0 条也报(空对话是真实状态)。 */

import type { PageProbe } from '@/bridge/pageContext';
import { useChatStore } from '@/stores/chatStore';

export const chatProvider: PageProbe = {
  page: 'chat',
  report() {
    const n = useChatStore.getState().messages.length;
    return { summary: `对话 · ${n} 条消息`, counts: { messages: n } };
  },
};
