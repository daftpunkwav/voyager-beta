/** 会话状态:消息流(user/agent/system)、任务进度卡、待答问题、连接与思考态。
 *
 * Chat 页与常驻悬浮窗是同一会话的两个视图(§10.12)，
 * 因此 store 放在 bridge 层被双方共享，避免 widget 直接依赖页面私有实现。
 */

import { create } from 'zustand';
import { routes } from '@/utils/routes';

export interface ChatMessage {
  seq: number;
  role: 'user' | 'agent' | 'system';
  content: string;
  proactive?: boolean;
  /** 主动消息出处(§9.8):greeting / followup / reach_out */
  kind?: string;
  /** 触发源短句(如「你打开了应用」),用户可见,不是 LLM 生成的解释 */
  reason?: string;
  ts?: number;
}

export interface ProgressCard {
  key: string; // source_id / job_id
  label: string;
  progress: number;
  stage: string;
  status: 'running' | 'completed' | 'failed';
  error?: string;
  /** payload 自带的资源类型(doc/repo/web…),决定能否跳资源详情页 */
  kind?: string;
  /** 预计算的资源详情路由;graph 的 job_id 无详情页则缺省(不做假按钮) */
  link?: string;
}

/** 笔记产物卡(note.created):点击跳 /notes?note=<id>。 */
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

/** agent.step 的实时步骤(phase-06):只显示当前一步,新步骤覆盖旧的。 */
export interface CurrentStep {
  /** 工具名或 round-N */
  name: string;
  /** 在干活的 subagent 名(chat / 派遣名) */
  subagent: string;
}

/** agent.observe 的观察提示(phase-12 §9.2):只留最新一条,新覆盖旧,不做 timeline。 */
export interface ObserveNotice {
  seq: number;
  content: string;
  /** 后端是否真的自动派了任务(如 auto-index) */
  acted: boolean;
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
  /** 当前工具步骤(agent.step);agent.message / 回合结束清掉 */
  currentStep: CurrentStep | null;
  /** 最近一条观察提示(agent.observe,phase-12);新覆盖旧,agent.message 不清掉 */
  observe: ObserveNotice | null;
  /** 历史接口消息(user.message/agent.message)→ 消息流;不触发思考态。 */
  applyHistory: (events: ChatEvent[]) => void;
  /** SSE 事件分发(agent.ask、task.* 、agent.message、note.created 等;纯状态迁移,可单测)。 */
  dispatch: (ev: ChatEvent) => void;
  appendLocal: (msg: ChatMessage) => void;
  /** 系统提示(急停/超时等控制面事件,本地 seq);不动 thinking,由调用方决定思考态。 */
  addSystem: (content: string) => void;
  setConnected: (v: boolean) => void;
  clearQuestion: () => void;
  setQuestion: (q: PendingQuestion | null) => void;
}

function taskKey(payload: Record<string, unknown>): string {
  return String(payload.source_id ?? payload.job_id ?? '');
}

/** 卡片标题优先级:project → title → kind → key。
 *  sources 进度事件常缺 project,直接用 key 会是一串 uuid,先用 kind 等可读字段兜住。 */
function taskLabel(payload: Record<string, unknown>, fallback: string): string {
  for (const field of ['project', 'title', 'kind'] as const) {
    const v = payload[field];
    if (v !== undefined && v !== null && String(v) !== '') return String(v);
  }
  return fallback;
}

/** source_id → 资源详情路由(§10.3);graph 等只有 job_id 的任务没有详情页,不造链接。
 *  kind 缺省时 sourceOf 落 repo 页:当前仅 repo worker 的 task 事件不带 kind,恰好正确。 */
function taskLink(payload: Record<string, unknown>): string | undefined {
  const sid = payload.source_id;
  if (sid === undefined || sid === null || String(sid) === '') return undefined;
  const kind = payload.kind === undefined ? undefined : String(payload.kind);
  return routes.sourceOf(kind, String(sid));
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  cards: {},
  cardOrder: [],
  artifacts: [],
  question: null,
  connected: false,
  thinking: false,
  currentStep: null,
  observe: null,

  applyHistory: (events) => {
    const msgs = events
      .filter((e) => e.type === 'user.message' || e.type === 'agent.message')
      .map((e) => ({
        seq: e.seq,
        role: (e.type === 'user.message' ? 'user' : 'agent') as ChatMessage['role'],
        content: String(e.payload.content ?? ''),
        proactive: Boolean(e.payload.proactive),
        // 主动出处(§9.8)随 payload 持久化,历史回放仍可见
        kind: e.payload.kind === undefined ? undefined : String(e.payload.kind),
        reason: e.payload.reason === undefined ? undefined : String(e.payload.reason),
        ts: e.ts,
      }));
    set({ messages: msgs });
  },

  dispatch: (ev) => {
    const p = ev.payload;
    switch (ev.type) {
      case 'agent.message': {
        // question 一并清掉:agent 继续说话说明已不再等答案(如回答超时后按默认继续),
        // 弹窗不能卡在已被后端丢弃的问题上(§9.15 超时兜底);
        // currentStep 同步清掉:回合有产出即不再"正在调工具"
        set({
          thinking: false,
          question: null,
          currentStep: null,
          messages: [
            ...get().messages,
            {
              seq: ev.seq,
              role: 'agent',
              content: String(p.content ?? ''),
              proactive: Boolean(p.proactive),
              kind: p.kind === undefined ? undefined : String(p.kind),
              reason: p.reason === undefined ? undefined : String(p.reason),
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
      case 'agent.step': {
        // 工具/轮次实时步骤:新步骤覆盖旧的,不做 trajectory(§9.2 的 06 切片)
        set({
          currentStep: {
            name: String(p.name ?? ''),
            subagent: String(p.subagent ?? ''),
          },
        });
        break;
      }
      case 'agent.observe': {
        // 观察提示(phase-12 §9.2):只留最新一条,不进 messages 时间线
        // (导入一堆仓库时不刷屏);agent.message 不清它,发完话仍可看见
        set({
          observe: {
            seq: ev.seq,
            content: String(p.content ?? ''),
            acted: Boolean(p.acted),
          },
        });
        break;
      }
      case 'task.progress':
      case 'task.enqueued': {
        const key = taskKey(p);
        if (!key) break;
        const cards = { ...get().cards };
        if (!cards[key]) get().cardOrder.push(key);
        const prev = cards[key];
        cards[key] = {
          key,
          label: taskLabel(p, prev?.label ?? key),
          progress: Number(p.progress ?? prev?.progress ?? 0),
          stage: String(p.stage ?? prev?.stage ?? '进行中'),
          status: 'running',
          kind: p.kind === undefined ? prev?.kind : String(p.kind),
          link: taskLink(p) ?? prev?.link,
        };
        set({ cards, cardOrder: [...get().cardOrder] });
        break;
      }
      case 'task.completed':
      case 'task.failed': {
        const key = taskKey(p);
        if (!key) break;
        const failed = ev.type === 'task.failed';
        const cards = { ...get().cards };
        const prev = cards[key];
        // 没有先到的 progress 卡也建卡:完成/失败是终态事实,不能因为缺前序就吞掉
        if (!prev) get().cardOrder.push(key);
        cards[key] = {
          key,
          label: taskLabel(p, prev?.label ?? key),
          progress: failed ? (prev?.progress ?? 0) : 1,
          stage: String(p.stage ?? (failed ? (prev?.stage ?? '') : '已完成')),
          status: failed ? 'failed' : 'completed',
          error: p.error ? String(p.error) : undefined,
          kind: p.kind === undefined ? prev?.kind : String(p.kind),
          link: taskLink(p) ?? prev?.link,
        };
        set({ cards, cardOrder: [...get().cardOrder] });
        break;
      }
      default:
        break;
    }
  },

  appendLocal: (msg) => {
    set({ thinking: true, messages: [...get().messages, msg] });
  },

  addSystem: (content) => {
    set({
      messages: [
        ...get().messages,
        { seq: -Date.now(), role: 'system', content },
      ],
    });
  },

  setConnected: (v) => set({ connected: v }),
  clearQuestion: () => set({ question: null }),
  setQuestion: (q) => set({ question: q }),
}));
