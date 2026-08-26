/** 活动 feed 的共享类型与摘要逻辑。
 *
 * FeedEvent / summarize 同时被 activity 页与 overview 活动卡消费，
 * 放在 bridge 层避免页面之间直接 import 私有实现(§10.1)。
 */

export interface FeedEvent {
  seq: number;
  id: string;
  type: string;
  actor: { kind: string; id: string };
  payload: Record<string, unknown>;
  ts: number;
  trace_id: string;
}

export type RowTone = 'normal' | 'error' | 'muted';

export interface RowSummary {
  text: string;
  tone: RowTone;
}

function clip(text: unknown, max = 60): string {
  const s = String(text ?? '');
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

function actorName(actor: FeedEvent['actor']): string {
  if (actor.kind === 'user') return '用户';
  if (actor.kind === 'agent') return actor.id || 'agent';
  return actor.id || 'system';
}

/** 按类型模板生成摘要;未识别类型灰字显示原文(开放集,不崩)。 */
export function summarize(ev: FeedEvent): RowSummary {
  const who = actorName(ev.actor);
  const p = ev.payload;
  switch (ev.type) {
    case 'user.message':
      return { text: `${who} 发消息:${clip(p.content)}`, tone: 'normal' };
    case 'agent.message':
      return { text: `${who} 回复:${clip(p.content)}`, tone: 'normal' };
    case 'user.online':
      return { text: `${who} 上线`, tone: 'muted' };
    case 'user.activity':
      return { text: `${who} 行为:${p.kind ?? ''} @ ${clip(p.page, 30)}`, tone: 'muted' };
    case 'note.created':
      return { text: `${who} 创建笔记《${clip(p.title, 40)}》`, tone: 'normal' };
    case 'note.edited':
      return { text: `${who} 编辑笔记 ${clip(p.note_id, 12)}`, tone: 'normal' };
    case 'note.deleted':
      return { text: `${who} 删除笔记《${clip(p.title, 40)}》`, tone: 'muted' };
    case 'source.added':
      return { text: `${who} 导入资源 ${clip(p.name ?? p.source_id, 40)}`, tone: 'normal' };
    case 'source.ready':
      return { text: `${who} 资源就绪 ${clip(p.name ?? p.source_id, 40)}`, tone: 'normal' };
    case 'source.removed':
      return { text: `${who} 移除资源 ${clip(p.source_id, 12)}`, tone: 'muted' };
    case 'task.enqueued':
      return { text: `${who} 任务入队 ${clip(p.project ?? p.source_id, 30)}`, tone: 'muted' };
    case 'task.progress': {
      const pct = Math.round(Number(p.progress ?? 0) * 100);
      return { text: `${who} 任务进度 ${pct}% · ${clip(p.stage, 20)}`, tone: 'muted' };
    }
    case 'task.completed':
      return { text: `${who} 任务完成 ${clip(p.project ?? p.source_id, 30)}`, tone: 'normal' };
    case 'task.failed':
      return { text: `${who} 任务失败:${clip(p.error, 60)}`, tone: 'error' };
    case 'settings.changed':
      return { text: `${who} 修改设置 ${clip(p.key, 40)}`, tone: 'normal' };
    case 'service.health.changed':
      return { text: `服务 ${clip(p.service, 20)} 状态 ${p.status ?? ''}`, tone: p.status === 'up' ? 'muted' : 'error' };
    case 'graph.engine.fallback':
      return { text: `图谱引擎回退:${clip(p.reason, 50)}`, tone: 'muted' };
    case 'agent.ask':
      return { text: `${who} 向用户提问`, tone: 'normal' };
    case 'agent.navigate':
      return { text: `${who} 跳转页面 ${clip(p.path ?? p.to, 20)}`, tone: 'muted' };
    default:
      return { text: ev.type, tone: 'muted' };
  }
}
