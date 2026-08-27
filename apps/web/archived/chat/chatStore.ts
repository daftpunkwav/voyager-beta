/** 聊天状态代理出口。
 *
 * 实际实现已迁移到 bridge/chatStore.ts(供 Chat 页与悬浮窗共享)。
 * 本文件保留以维持既有 import 路径兼容。
 */

export {
  type ChatMessage,
  type ChatEvent,
  type PendingQuestion,
  type ProgressCard,
  type NoteArtifact,
  useChatStore,
} from '@/bridge/chatStore';
