/** 事件行:类型摘要一句话 + actor 徽标(人/agent/系统三色)+ 详情展开 +
 * 撤销按钮(补偿表内且能力可用;note.edited 置灰"暂不支持")。
 */

import { useState } from 'react';
import { COMPENSATIONS } from './activityStore';
import { type FeedEvent, summarize } from '@/bridge/feed';

export { type FeedEvent, summarize } from '@/bridge/feed';

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
