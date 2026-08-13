/**
 * Agent 域 — Agent 会话 / 用户画像 / 记忆 / 权限 / SSE 对话(chat/question/analyze/note/import-assist/graph-guide)
 *   19 个方法,包含较大 Adapter 转换(数字 id → 字符串,agent 枚举归一化)
 */
import type {
  AgentId,
  AgentMessage,
  AgentPermissions,
  AgentProfile,
  AgentSession,
  ApiResponse,
  ContextWindowStats,
  ImportAssistContext,
  QuestionAnswer,
  SSEEvent,
  UserProfile,
} from '@/api/types';
import { parseSSEStream } from '@/utils/sse-parser';
import type { HttpCtx } from './http-ctx';

/** 规整化后端返回的 AgentSession(数字 id → string,默认值,源标识) */
function normalizeSession<T extends AgentSession>(s: T): T {
  return {
    ...s,
    id: String(s.id),
    agent: s.agent as AgentId,
    project_id: s.project_id ? String(s.project_id) : null,
    project_ids: (s.project_ids ?? []).map(String),
    source: s.source ?? 'chat',
  };
}

/** 规整化 AgentSession 内嵌的 messages 数组 */
function normalizeMessages(messages: AgentMessage[]): AgentMessage[] {
  return messages.map((m) => ({
    ...m,
    id: String(m.id),
    session_id: String(m.session_id),
    agent: m.agent as AgentId,
    content: m.content ?? '',
    ...(typeof m.thinking === 'string' && m.thinking.trim() ? { thinking: m.thinking } : {}),
    ...(Array.isArray(m.tool_calls) && m.tool_calls.length ? { tool_calls: m.tool_calls } : {}),
    ...(Array.isArray(m.subagents) && m.subagents.length ? { subagents: m.subagents } : {}),
  }));
}

export class AgentApi {
  constructor(private readonly ctx: HttpCtx) {}

  async listAgentSessions(): Promise<ApiResponse<AgentSession[]>> {
    const res = await this.ctx.apiRequest<AgentSession[]>('/agent/sessions');
    return {
      data: res.data.map(normalizeSession),
      meta: res.meta,
    };
  }

  async getAgentSession(
    id: string
  ): Promise<ApiResponse<AgentSession & { messages: AgentMessage[] }>> {
    const res = await this.ctx.apiRequest<AgentSession & { messages: AgentMessage[] }>(
      `/agent/sessions/${id}`
    );
    const base = normalizeSession(res.data);
    return {
      data: {
        ...base,
        messages: normalizeMessages(res.data.messages),
      },
      meta: res.meta,
    };
  }

  async createAgentSession(): Promise<ApiResponse<AgentSession>> {
    const res = await this.ctx.apiRequest<AgentSession>('/agent/sessions', { method: 'POST' });
    return {
      data: normalizeSession(res.data),
      meta: res.meta,
    };
  }

  async deleteAgentSession(id: string): Promise<ApiResponse<{ success: boolean }>> {
    return this.ctx.apiRequest(`/agent/sessions/${id}`, { method: 'DELETE' });
  }

  async updateAgentSession(
    id: string,
    data: { title?: string; project_id?: string | null; project_ids?: string[] }
  ): Promise<ApiResponse<AgentSession>> {
    const res = await this.ctx.apiRequest<AgentSession>(`/agent/sessions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
    return {
      data: normalizeSession(res.data),
      meta: res.meta,
    };
  }

  async getAgentProfiles(): Promise<ApiResponse<AgentProfile[]>> {
    const res = await this.ctx.apiRequest<AgentProfile[]>('/agent/profiles');
    return {
      data: res.data.map((p) => ({ ...p, id: p.id as AgentId })),
      meta: res.meta,
    };
  }

  /** 当前会话的上下文窗口用量 */
  async getContextWindow(sessionId?: string | null): Promise<ApiResponse<ContextWindowStats>> {
    return this.ctx.apiRequest<ContextWindowStats>('/agent/context-window', {}, {
      session_id: sessionId ?? undefined,
    });
  }

  async *chatAgent(
    sessionId: string,
    message: string,
    signal?: AbortSignal
  ): AsyncGenerator<SSEEvent> {
    const res = await this.ctx.apiSSE(`/agent/sessions/${sessionId}/chat`, { message }, signal);
    if (!res.body) return;
    const reader = res.body.getReader();
    yield* parseSSEStream(reader, signal);
  }

  async *answerQuestion(
    sessionId: string,
    questionId: string,
    answers: QuestionAnswer[],
    signal?: AbortSignal,
    skipped = false
  ): AsyncGenerator<SSEEvent> {
    const res = await this.ctx.apiSSE(
      '/agent/question',
      {
        session_id: sessionId,
        question_id: questionId,
        answers,
        skipped,
      },
      signal
    );
    if (!res.body) return;
    const reader = res.body.getReader();
    yield* parseSSEStream(reader, signal);
  }

  async *analyzeProject(
    projectId: string,
    agent?: AgentId,
    signal?: AbortSignal
  ): AsyncGenerator<SSEEvent> {
    const depth = agent === 'mentor' ? 'deep' : 'quick';
    const res = await this.ctx.apiSSE(
      `/agent/analyze/${projectId}`,
      {
        depth,
        force_refresh: false,
        // 透传专家 Agent;后端缺省时仍可按 depth 兼容
        agent_id: agent && agent !== 'hub' ? agent : undefined,
      },
      signal
    );
    if (!res.body) return;
    const reader = res.body.getReader();
    yield* parseSSEStream(reader, signal);
  }

  /** Scribe 生成项目大纲/草稿(SSE) */
  async *generateNote(
    projectId: string,
    params?: { mode?: 'project' | 'standalone'; topic?: string },
    signal?: AbortSignal
  ): AsyncGenerator<SSEEvent> {
    const res = await this.ctx.apiSSE(
      '/agent/note/generate',
      {
        project_id: projectId,
        mode: params?.mode ?? 'project',
        topic: params?.topic,
      },
      signal
    );
    if (!res.body) return;
    const reader = res.body.getReader();
    yield* parseSSEStream(reader, signal);
  }

  /** 导入助手对话(SSE) */
  async *importAssistChat(
    message: string,
    context: ImportAssistContext,
    signal?: AbortSignal
  ): AsyncGenerator<SSEEvent> {
    const res = await this.ctx.apiSSE('/agent/import-assist', { message, context }, signal);
    if (!res.body) return;
    const reader = res.body.getReader();
    yield* parseSSEStream(reader, signal);
  }

  /** 图谱向导对话(SSE,专用 Atlas Agent) */
  async *graphGuideChat(
    message: string,
    context?: { selected_node_id?: string | null },
    signal?: AbortSignal
  ): AsyncGenerator<SSEEvent> {
    const res = await this.ctx.apiSSE(
      '/agent/graph-guide',
      {
        message,
        selected_node_id: context?.selected_node_id ?? null,
      },
      signal
    );
    if (!res.body) return;
    const reader = res.body.getReader();
    yield* parseSSEStream(reader, signal);
  }

  async getUserProfile(): Promise<ApiResponse<UserProfile>> {
    return this.ctx.apiRequest<UserProfile>('/user/profile');
  }

  async updateUserProfile(data: Partial<UserProfile>): Promise<ApiResponse<UserProfile>> {
    return this.ctx.apiRequest<UserProfile>('/user/profile', {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  /** 清除 Agent 关于用户的画像记忆(不删除对话) */
  async clearUserMemory(): Promise<ApiResponse<UserProfile>> {
    return this.ctx.apiRequest<UserProfile>('/user/profile/clear-memory', {
      method: 'POST',
    });
  }

  /** 确认待处理记忆提案 */
  async acceptMemoryProposal(proposalId: string): Promise<ApiResponse<UserProfile>> {
    return this.ctx.apiRequest<UserProfile>(
      `/user/profile/memory-proposals/${encodeURIComponent(proposalId)}/accept`,
      { method: 'POST' }
    );
  }

  /** 拒绝待处理记忆提案 */
  async rejectMemoryProposal(proposalId: string): Promise<ApiResponse<UserProfile>> {
    return this.ctx.apiRequest<UserProfile>(
      `/user/profile/memory-proposals/${encodeURIComponent(proposalId)}/reject`,
      { method: 'POST' }
    );
  }

  async getPermissions(): Promise<ApiResponse<AgentPermissions>> {
    return this.ctx.apiRequest<AgentPermissions>('/agent/permissions');
  }
}
