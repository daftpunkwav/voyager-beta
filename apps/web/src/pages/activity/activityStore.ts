/** 活动页状态:gateway feed(after_seq 游标升序拉取)+ 分组筛选 + 轮询增量。
 *
 * 数据源只有事件日志(不建业务表,§7.6 审计的可视化);
 * 首屏带 limit 翻页到最新(最多 5 页,不许一次拉全表,坑 1);
 * 撤销是补偿操作(调反向能力),不是回滚。
 */

import { create } from 'zustand';
import { callCapability } from '@/bridge/client';
import { type FeedEvent } from '@/bridge/feed';

export { type FeedEvent } from '@/bridge/feed';

export type EventGroup = 'all' | 'chat' | 'notes' | 'sources' | 'tasks' | 'system';

/** 筛选器清单(与 contracts + 各服务 service.json 对齐;硬编码只是筛选器)。 */
export const GROUP_TYPES: Record<Exclude<EventGroup, 'all'>, string[]> = {
  chat: ['user.message', 'agent.message', 'agent.ask', 'agent.navigate',
    'user.online', 'user.activity'],
  notes: ['note.created', 'note.edited', 'note.deleted'],
  sources: ['source.added', 'source.ready', 'source.removed'],
  tasks: ['task.enqueued', 'task.progress', 'task.completed', 'task.failed'],
  system: ['settings.changed', 'service.health.changed', 'graph.engine.fallback'],
};

/** 补偿操作表(§5.3):撤销 = 调反向能力;不可逆事件无入口。 */
export interface Compensation {
  domain: string;
  capability: string;
  args: (payload: Record<string, unknown>) => Record<string, unknown>;
  confirmText: string;
}

export const COMPENSATIONS: Partial<Record<string, Compensation>> = {
  'note.created': {
    domain: 'notes',
    capability: 'delete_note',
    args: (p) => ({ note_id: String(p.note_id ?? '') }),
    confirmText: '撤销将删除该笔记(执行反向操作,不可逆)',
  },
  'source.added': {
    domain: 'sources',
    capability: 'remove_repo',
    args: (p) => ({ repo_id: String(p.source_id ?? '') }),
    confirmText: '撤销将移除该资源并清理本地克隆(执行反向操作)',
  },
};

export const MAX_ROWS = 500;
const PAGE_LIMIT = 200;
const MAX_PAGES = 5;
export const POLL_MS = 5000;

async function fetchFeed(
  afterSeq: number,
  group: EventGroup,
): Promise<FeedEvent[]> {
  const types = group === 'all' ? '' : GROUP_TYPES[group].join(',');
  const url = `/api/activity/feed?after_seq=${afterSeq}&types=${encodeURIComponent(types)}&limit=${PAGE_LIMIT}`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`feed ${resp.status}`);
  const body = (await resp.json()) as { events: FeedEvent[] };
  return body.events ?? [];
}

interface ActivityState {
  events: FeedEvent[]; // 升序;渲染层 reverse 取最新
  cursor: number; // 已拉到的最大 seq(轮询游标)
  group: EventGroup;
  loading: boolean;
  error: { code: string; message: string } | null;
  /** 已确认可用的补偿能力("domain.capability"),服务能力清单数据源 */
  caps: Set<string>;
  init: () => Promise<void>;
  setGroup: (group: EventGroup) => void;
  refresh: () => Promise<void>;
  loadCaps: () => Promise<void>;
  undo: (event: FeedEvent) => Promise<void>;
}

/** 合并去重(轮询重放安全):按 seq 去重、升序、超上限截旧。纯函数可单测。 */
export function append(events: FeedEvent[], incoming: FeedEvent[]): {
  events: FeedEvent[];
  cursor: number;
} {
  const seen = new Set(events.map((e) => e.seq));
  const merged = [...events];
  for (const e of incoming) {
    if (!seen.has(e.seq)) {
      merged.push(e);
      seen.add(e.seq);
    }
  }
  merged.sort((a, b) => a.seq - b.seq);
  return { events: merged.slice(-MAX_ROWS), cursor: merged[merged.length - 1]?.seq ?? 0 };
}

export const useActivityStore = create<ActivityState>((set, get) => ({
  events: [],
  cursor: 0,
  group: 'all',
  loading: false,
  error: null,
  caps: new Set(),

  init: async () => {
    set({ loading: true, error: null, events: [], cursor: 0 });
    try {
      // 首屏翻页到最新(升序窗口每次最多 200;事件量大时最多 5 页)
      let events: FeedEvent[] = [];
      let cursor = 0;
      for (let page = 0; page < MAX_PAGES; page += 1) {
        const batch = await fetchFeed(cursor, get().group);
        if (batch.length === 0) break;
        const next = append(events, batch);
        events = next.events;
        cursor = next.cursor;
        if (batch.length < PAGE_LIMIT) break;
      }
      set({ events, cursor, loading: false });
      void get().loadCaps();
    } catch (err) {
      set({ loading: false, error: { code: 'GATEWAY.UNAVAILABLE', message: (err as Error).message } });
    }
  },

  setGroup: (group) => {
    set({ group });
    void get().init();
  },

  refresh: async () => {
    if (get().loading) return;
    try {
      const incoming = await fetchFeed(get().cursor, get().group);
      if (incoming.length > 0) set(append(get().events, incoming));
      set({ error: null });
    } catch {
      // 轮询失败不打扰(下一轮再试);连续失败由页面降级提示
    }
  },

  loadCaps: async () => {
    // 能力清单经 GET /api/<domain>/capabilities(reversible 元数据入口,§5.3);
    // 只取补偿表涉及的域,决定撤销按钮可用性
    const domains = [...new Set(Object.values(COMPENSATIONS)
      .filter((c): c is Compensation => c != null)
      .map((c) => c.domain))];
    const caps = new Set<string>();
    await Promise.all(
      domains.map(async (d) => {
        try {
          const resp = await fetch(`/api/${d}/capabilities`);
          if (!resp.ok) return;
          const body = (await resp.json()) as { capabilities?: { name: string }[] };
          for (const c of body.capabilities ?? []) caps.add(`${d}.${c.name}`);
        } catch {
          // 单个域失败只影响该域撤销按钮
        }
      }),
    );
    set({ caps });
  },

  undo: async (event) => {
    const comp = COMPENSATIONS[event.type];
    if (!comp) return;
    await callCapability(comp.domain, comp.capability, comp.args(event.payload));
    await get().refresh(); // 补偿后立即追平(note.deleted 等)
  },
}));
