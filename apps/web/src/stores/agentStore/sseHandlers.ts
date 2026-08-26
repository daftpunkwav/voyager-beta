// @ts-nocheck — 迁移期:RepoPilot 风格代码,新 page / hook 仍按 strict 写(见各文件顶部注释)。
/**
 * SSE 事件处理器（§4.1.10 N-01 拆分）
 *
 * 把 processSSEStream 中各事件 case 的副作用抽到独立纯函数。
 * 主体 store 调用 HANDLERS[event.event](event, ctx) 即可完成分派。
 *
 * 设计目标：
 * - 保持原逻辑逐行等价（不改语义、不改 set 顺序）
 * - 每个 handler 独立可单测
 * - 不持有 store 内部状态；通过 ctx.set / ctx.get 访问
 *
 * 注意：tool_call / tool_result / question / agent_switch / subagent_start /
 * subagent_done / session_projects 涉及 sawQuestion/withFlushedPrior/buildOffer/
 * recoverQuestionFromText 等闭包依赖，仍在 store 主体内处理；本文件覆盖
 * 无状态副作用或仅简单 state patch 的 6 类事件。
 */
import {
  asSSEError,
  asSSETextDelta,
  asSSEThinking,
} from '@/utils/sse-helpers';

/** handler 实际操作的 store 状态子集（最小形状，避免与主体 store 类型循环依赖） */
export interface SseHandlerState {
  streamingContent: string;
  thinkingBuffer: string;
  error: string | null;
  streaming: boolean;
  subagents: Array<{ agentId: string; thinking?: string; output?: string }>;
}

/** 处理器上下文。
 *  主体 store 在每次 processSSEStream 调用时构造一个 ctx 并传给各 handler。
 *  后续可扩展为 ctx.sawQuestion / ctx.buildOffer 等。
 */
export interface SseHandlerCtx<TState extends object = SseHandlerState> {
  set: (
    partial: Partial<TState> | ((s: TState) => Partial<TState>),
  ) => void;
  get: () => TState;
}

export type SseHandler<TState extends object = SseHandlerState> = (
  event: { event: string; data: unknown },
  ctx: SseHandlerCtx<TState>,
) => void | Promise<void>;

export const handleTextDelta: SseHandler = (event, ctx) => {
  // §4.1.10: 从原 processSSEStream case text_delta 迁出
  const delta = asSSETextDelta(event.data as Record<string, unknown>);
  const piece = delta.content ?? '';
  if (!piece) return;
  ctx.set((state) => ({
    streamingContent: state.streamingContent + piece,
  }));
};

export const handleThinking: SseHandler = (event, ctx) => {
  // §4.1.10: 从原 processSSEStream case thinking 迁出
  const thinking = asSSEThinking(event.data as Record<string, unknown>);
  ctx.set((state) => ({
    thinkingBuffer: state.thinkingBuffer + (thinking.content ?? ''),
  }));
};

export const handleSubagentThinking: SseHandler = (event, ctx) => {
  // §4.1.10: 从原 processSSEStream case subagent_thinking 迁出
  const raw = event.data as Record<string, unknown>;
  const agentId = typeof raw.agent_id === 'string' ? raw.agent_id : '';
  const content = typeof raw.content === 'string' ? raw.content : '';
  if (!agentId || !content) return;
  ctx.set((state) => ({
    subagents: state.subagents.map((s) =>
      s.agentId === agentId
        ? { ...s, thinking: (s.thinking || '') + content }
        : s,
    ),
  }));
};

export const handleSubagentText: SseHandler = (event, ctx) => {
  // §4.1.10: 从原 processSSEStream case subagent_text 迁出
  const raw = event.data as Record<string, unknown>;
  const agentId = typeof raw.agent_id === 'string' ? raw.agent_id : '';
  const content = typeof raw.content === 'string' ? raw.content : '';
  if (!agentId || !content) return;
  ctx.set((state) => ({
    subagents: state.subagents.map((s) =>
      s.agentId === agentId
        ? { ...s, output: (s.output || '') + content }
        : s,
    ),
  }));
};

export const handleError: SseHandler = (event, ctx) => {
  // §4.1.10: 从原 processSSEStream case error 迁出
  const errData = asSSEError(event.data as Record<string, unknown>);
  ctx.set({ error: errData.message, streaming: false });
};

export const handleDone: SseHandler = () => {
  // §4.1.10: 从原 processSSEStream case done 迁出（仅中间信号，主流程在循环结束后统一落库）
};

/** 处理器路由表。
 *  复杂事件（tool_call/tool_result/question/agent_switch/subagent_start/
 *  subagent_done/session_projects）暂时未迁移，仍在 processSSEStream
 *  主体内；后续 PR 跟进。
 */
export const HANDLERS: Record<string, SseHandler<SseHandlerState>> = {
  text_delta: handleTextDelta,
  thinking: handleThinking,
  subagent_thinking: handleSubagentThinking,
  subagent_text: handleSubagentText,
  error: handleError,
  done: handleDone,
};
