/** 事件行:类型摘要一句话 + actor 徽标(人/agent/系统三色)+ 详情展开 +
 * 撤销按钮(补偿表内且能力可用;note.edited 置灰"暂不支持")。
 */

import { useState } from 'react';
import { COMPENSATIONS, type FeedEvent } from './activityStore';

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

const KIND_LABELS: Record<string, string> = {
  user: '用户',
  agent: 'agent',
  system: '系统',
};

export function EventRow({
  event,
  canUndo,
  onUndo,
}: {
  event: FeedEvent;
  canUndo: boolean;
  onUndo: (event: FeedEvent) => void;
}) {
  const [open, setOpen] = useState(false);
  const [armed, setArmed] = useState(false);
  const summary = summarize(event);
  const comp = COMPENSATIONS[event.type];
  const unsupported = event.type === 'note.edited'; // 无快照,诚实置灰(§5.3)

  const time = new Date(event.ts * 1000).toLocaleTimeString('zh-CN', { hour12: false });

  return (
    <div className={`event-row event-row--${summary.tone}`}>
      <span className={`event-row__actor event-row__actor--${event.actor.kind}`}>
        {KIND_LABELS[event.actor.kind] ?? event.actor.kind}
      </span>
      <button
        type="button"
        className="event-row__body"
        onClick={() => setOpen((v) => !v)}
        title="点击展开/收起详情"
      >
        <span className="event-row__text">{summary.text}</span>
        <span className="event-row__time mono">{time}</span>
        {open ? (
          <pre className="event-row__detail mono">{JSON.stringify(event.payload, null, 2)}</pre>
        ) : null}
      </button>
      {comp && canUndo ? (
        armed ? (
          <span className="event-row__confirm">
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => {
                setArmed(false);
                onUndo(event);
              }}
            >
              确认撤销
            </button>
            <button type="button" className="btn btn-sm" onClick={() => setArmed(false)}>
              取消
            </button>
          </span>
        ) : (
          <button
            type="button"
            className="btn btn-sm"
            title={comp.confirmText}
            onClick={() => setArmed(true)}
          >
            撤销
          </button>
        )
      ) : null}
      {unsupported ? (
        <span className="small muted event-row__unsupported" title="编辑无快照,暂不支持撤销">
          暂不支持
        </span>
      ) : null}
    </div>
  );
}
