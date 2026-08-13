import type {
  SSEAgentSwitch,
  SSEError,
  SSEEvent,
  SSESubagentDone,
  SSESubagentStart,
  SSEToolCall,
  SSEToolResult,
  SSETextDelta,
  SSEThinking,
} from '@/api/types';

export function asSSETextDelta(data: Record<string, unknown>): SSETextDelta {
  return data as unknown as SSETextDelta;
}

export function asSSEThinking(data: Record<string, unknown>): SSEThinking {
  return data as unknown as SSEThinking;
}

export function asSSEToolCall(data: Record<string, unknown>): SSEToolCall {
  return data as unknown as SSEToolCall;
}

export function asSSEToolResult(data: Record<string, unknown>): SSEToolResult {
  return data as unknown as SSEToolResult;
}

export function asSSEAgentSwitch(data: Record<string, unknown>): SSEAgentSwitch {
  return data as unknown as SSEAgentSwitch;
}

export function asSSESubagentStart(data: Record<string, unknown>): SSESubagentStart {
  return data as unknown as SSESubagentStart;
}

export function asSSESubagentDone(data: Record<string, unknown>): SSESubagentDone {
  return data as unknown as SSESubagentDone;
}

export function asSSEError(data: Record<string, unknown>): SSEError {
  return data as unknown as SSEError;
}

export function getEventData<T>(event: SSEEvent): T {
  return event.data as unknown as T;
}
