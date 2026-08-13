/**
 * 可复用的 Agent SSE 流消费器。
 * 主聊天、导入助手、图谱向导、详情分析等均可共用。
 */
import type { SSEEvent } from '@/api/types';
import { asSSETextDelta, asSSEThinking } from '@/utils/sse-helpers';

export interface AgentStreamHandlers {
  onTextDelta?: (piece: string, fullText: string) => void;
  onThinking?: (piece: string, fullThinking: string) => void;
  onSelectRepos?: (data: Record<string, unknown>) => void;
  onToolCall?: (data: Record<string, unknown>) => void;
  onToolResult?: (data: Record<string, unknown>) => void;
  onAgentSwitch?: (data: Record<string, unknown>) => void;
  onDone?: (data: Record<string, unknown>) => void;
  onError?: (message: string, data?: Record<string, unknown>) => void;
  /** 任意事件兜底钩子 */
  onEvent?: (event: SSEEvent) => void;
}

export interface AgentStreamResult {
  text: string;
  thinking: string;
  sawError: boolean;
  errorMessage: string;
  /** SSE error 事件中的报错码（若有） */
  errorCode: string | null;
  doneData: Record<string, unknown> | null;
}

/**
 * 消费 Agent SSE 流，聚合 text / thinking，并分发到 handlers。
 * 不负责 UI 状态；调用方可在 onTextDelta 中节流刷新界面。
 */
export async function consumeAgentSSEStream(
  stream: AsyncIterable<SSEEvent>,
  handlers: AgentStreamHandlers = {},
  options?: { signal?: AbortSignal },
): Promise<AgentStreamResult> {
  let text = '';
  let thinking = '';
  let sawError = false;
  let errorMessage = '';
  let errorCode: string | null = null;
  let doneData: Record<string, unknown> | null = null;
  const signal = options?.signal;

  for await (const event of stream) {
    if (signal?.aborted) break;
    handlers.onEvent?.(event);

    switch (event.event) {
      case 'text_delta': {
        const piece = asSSETextDelta(event.data).content ?? '';
        if (piece) {
          text += piece;
          handlers.onTextDelta?.(piece, text);
        }
        break;
      }
      case 'thinking': {
        const piece = asSSEThinking(event.data).content ?? '';
        if (piece) {
          // 仅对「新状态行」插换行；模型 reasoning 的连续 token 不打断
          const looksLikeStatusLine = /^\s*[【[]/.test(piece);
          if (
            looksLikeStatusLine &&
            thinking &&
            !thinking.endsWith('\n') &&
            !piece.startsWith('\n')
          ) {
            thinking += '\n';
          }
          thinking += piece;
          handlers.onThinking?.(piece, thinking);
        }
        break;
      }
      case 'select_repos': {
        handlers.onSelectRepos?.(event.data as Record<string, unknown>);
        break;
      }
      case 'tool_call': {
        handlers.onToolCall?.(event.data as Record<string, unknown>);
        break;
      }
      case 'tool_result': {
        handlers.onToolResult?.(event.data as Record<string, unknown>);
        break;
      }
      case 'agent_switch': {
        handlers.onAgentSwitch?.(event.data as Record<string, unknown>);
        break;
      }
      case 'done': {
        doneData = event.data as Record<string, unknown>;
        handlers.onDone?.(doneData);
        break;
      }
      case 'error': {
        sawError = true;
        const data = event.data as { message?: string; code?: string };
        errorMessage = data?.message ?? '助手返回错误，请稍后再试。';
        errorCode = typeof data?.code === 'string' ? data.code : null;
        handlers.onError?.(errorMessage, event.data as Record<string, unknown>);
        break;
      }
      default:
        break;
    }
  }

  return { text, thinking, sawError, errorMessage, errorCode, doneData };
}
