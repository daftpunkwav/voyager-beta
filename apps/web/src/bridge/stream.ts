/** SSE 事件流:单例 EventSource + 模式订阅;断线带最后 seq 重连。 */

export interface StreamEvent {
  seq: number;
  type: string;
  actor?: Record<string, unknown>;
  payload: Record<string, unknown>;
  trace_id?: string;
  ts?: number;
}

type Handler = (event: StreamEvent) => void;

let source: EventSource | null = null;
let lastSeq = 0;
let started = false;
const handlers = new Set<{ patterns: string[]; fn: Handler }>();

function connect(): void {
  // after_seq = lastSeq:重连后由日志补齐断线期间的事件,不丢消息(§7.2)
  const url = lastSeq > 0 ? `/api/chat/stream?after_seq=${lastSeq}` : '/api/chat/stream';
  const es = new EventSource(url);
  source = es;
  es.onmessage = (msg) => {
    try {
      const event = JSON.parse(msg.data) as StreamEvent;
      const seq =
        typeof event.seq === 'number'
          ? event.seq
          : Number.parseInt(msg.lastEventId, 10);
      if (Number.isFinite(seq) && seq > lastSeq) {
        lastSeq = seq;
      }
      for (const h of handlers) {
        if (h.patterns.some((p) => matchPattern(p, event.type))) h.fn(event);
      }
    } catch {
      // 非 JSON 帧忽略(心跳注释帧不会进 onmessage)
    }
  };
  es.onerror = () => {
    // 浏览器原生 EventSource 会自动重连,但不带 after_seq;改为手动重建以续传
    es.close();
    if (handlers.size > 0) {
      setTimeout(connect, 1000);
    } else {
      started = false;
      source = null;
    }
  };
}

function matchPattern(pattern: string, type: string): boolean {
  // fnmatch 语义:*.xxx / xxx.* / 全等
  const re = new RegExp(
    '^' + pattern.split('*').map(escapeRe).join('.*') + '$',
  );
  return re.test(type);
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** 订阅事件(支持 *.type 通配);返回取消函数。首个订阅者建立连接,全部取消后断开。 */
export function subscribe(patterns: string[], fn: Handler): () => void {
  const entry = { patterns, fn };
  handlers.add(entry);
  if (!started) {
    started = true;
    connect();
  }
  return () => {
    handlers.delete(entry);
    if (handlers.size === 0 && source) {
      source.close();
      source = null;
      started = false;
    }
  };
}

/** 一次性追平 afterSeq 之后的存量事件(不保持长连)。 */
export async function replay(afterSeq: number, onEvent: Handler): Promise<void> {
  const resp = await fetch(`/api/chat/stream?after_seq=${afterSeq}&once=true`);
  const text = await resp.text();
  for (const frame of text.split('\n\n')) {
    const data = frame.split('\n').find((l) => l.startsWith('data: '));
    if (!data) continue;
    try {
      onEvent(JSON.parse(data.slice(6)) as StreamEvent);
    } catch {
      // 忽略坏帧
    }
  }
}
