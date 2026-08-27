/** 会话状态:消息流(user/agent/system)、任务进度卡、待答问题、连接与思考态。
 *
 * Chat 页与常驻悬浮窗是同一会话的两个视图(§10.12)，
 * 因此 store 放在 bridge 层被双方共享，避免 widget 直接依赖页面私有实现。
 */

import { create } from 'zustand';

export interface ChatMessage {
  seq: number;
  role: 'user' | 'agent' | 'system';
  content: string;
  proactive?: boolean;
  ts?: number;
}

export interface ProgressCard {
  key: string; // source_id / job_id
  label: string;
  progress: number;
  stage: string;
  status: 'running' | 'completed' | 'failed';
  error?: string;
}

/** 笔记产物卡(note.created):点击跳 /notes?open=<id>。 */
export interface NoteArtifact {
  seq: number;
  noteId: string;
  title: string;
}

export interface PendingQuestion {
  questionId: string;
  prompt: string;
  kind: 'text' | 'choice' | 'slider' | 'confirm';
  options: string[];
  min: number | null;
  max: number | null;
}

/** SSE 帧 / 历史行的公共形态(Event.to_dict + seq)。 */
export interface ChatEvent {
  seq: number;
  type: string;
  payload: Record<string, unknown>;
  ts?: number;
  trace_id?: string;
}

interface ChatState {
  messages: ChatMessage[];
  cards: Record<string, ProgressCard>;
  cardOrder: string[];
  artifacts: NoteArtifact[];
  question: PendingQuestion | null;
  connected: boolean;
  thinking: boolean;
  /** 历史接口消息(user.message/agent.message)→ 消息流;不触发思考态。 */
  applyHistory: (events: ChatEvent[]) => void;
  /** SSE 事件分发(agent.ask、task.* 、agent.message、note.created 等;纯状态迁移,可单测)。 */
  dispatch: (ev: ChatEvent) => void;
  appendLocal: (msg: ChatMessage) => void;
  setConnected: (v: boolean) => void;
  clearQuestion: () => void;
  setQuestion: (q: PendingQuestion | null) => void;
}

function taskKey(payload: Record<string, unknown>): string {
  return String(payload.source_id ?? payload.job_id ?? '');
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  cards: {},
  cardOrder: [],
  artifacts: [],
  question: null,
  connected: false,
  thinking: false,

  applyHistory: (events) => {
    const msgs = events
      .filter((e) => e.type === 'user.message' || e.type === 'agent.message')
      .map((e) => ({
        seq: e.seq,
        role: (e.type === 'user.message' ? 'user' : 'agent') as ChatMessage['role'],
        content: String(e.payload.content ?? ''),
        proactive: Boolean(e.payload.proactive),
        ts: e.ts,
      }));
    set({ messages: msgs });
  },

  dispatch: (ev) => {
    const p = ev.payload;
    switch (ev.type) {
      case 'agent.message': {
        set({
          thinking: false,
          messages: [
            ...get().messages,
            {
              seq: ev.seq,
              role: 'agent',
              content: String(p.content ?? ''),
              proactive: Boolean(p.proactive),
              ts: ev.ts,
            },
          ],
        });
        break;
      }
      case 'agent.ask': {
        set({
          question: {
            questionId: String(p.question_id),
            prompt: String(p.prompt ?? ''),
            kind: (p.kind as PendingQuestion['kind']) ?? 'confirm',
            options: (p.options as string[]) ?? [],
            min: (p.min as number | null) ?? null,
            max: (p.max as number | null) ?? null,
          },
        });
        break;
      }
      case 'agent.navigate': {
        set({
          messages: [
            ...get().messages,
            {
              seq: ev.seq,
              role: 'system',
              content: `已跳转:${String(p.path ?? '')}`,
              ts: ev.ts,
            },
          ],
        });
        break;
      }
      case 'note.created': {
        // 笔记产物卡(用户或 agent 落库都会出现;点击跳笔记页)
        set({
          artifacts: [
            ...get().artifacts,
            {
              seq: ev.seq,
              noteId: String(p.note_id ?? ''),
              title: String(p.title ?? '未命名笔记'),
            },
          ].filter((a) => a.noteId),
        });
        break;
      }
      case 'task.progress':
      case 'task.enqueued': {
        const key = taskKey(p);
        if (!key) break;
        const cards = { ...get().cards };
        if (!cards[key]) get().cardOrder.push(key);
        cards[key] = {
          key,
          label: String(p.project ?? key),
          progress: Number(p.progress ?? 0),
          stage: String(p.stage ?? 'running'),
          status: 'running',
        };
        set({ cards, cardOrder: [...get().cardOrder] });
        break;
      }
      case 'task.completed':
      case 'task.failed': {
        const key = taskKey(p);
        if (!key) break;
        const prev = get().cards[key];
        if (!prev) break;
        set({
          cards: {
            ...get().cards,
            [key]: {
              ...prev,
              progress: ev.type === 'task.completed' ? 1 : prev.progress,
              status: ev.type === 'task.completed' ? 'completed' : 'failed',
              error: p.error ? String(p.error) : undefined,
            },
          },
        });
        break;
      }
      default:
        break;
    }
  },

  appendLocal: (msg) => {
    set({ thinking: true, messages: [...get().messages, msg] });
  },

  setConnected: (v) => set({ connected: v }),
  clearQuestion: () => set({ question: null }),
  setQuestion: (q) => set({ question: q }),
}));
