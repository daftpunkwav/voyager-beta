/** 活动页:全系统事件时间线(gateway feed 重建,不建业务表)。
 * 分组筛选 chips + 5s 轮询增量(after_seq 游标)+ CSS content-visibility
 * 长列表渲染优化。user.activity 默认不在首屏刷屏(坑 2:它属于"对话"组)。
 */

import { useEffect, useMemo } from 'react';
import { Degraded } from '@/shell/Degraded';
import {
  COMPENSATIONS,
  POLL_MS,
  useActivityStore,
  type EventGroup,
} from './activityStore';
import { EventRow } from './EventRow';

const GROUPS: { key: EventGroup; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'chat', label: '对话' },
  { key: 'notes', label: '笔记' },
  { key: 'sources', label: '资源' },
  { key: 'tasks', label: '任务' },
  { key: 'system', label: '系统' },
];

export function ActivityPage() {
  const { loading, error, events, group, init, setGroup, refresh, caps, undo } =
    useActivityStore();

  useEffect(() => {
    void init();
  }, [init]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refresh();
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  // 最新在上(事件日志升序,渲染反转);超过 MAX_ROWS 的旧事件已被 store 截断
  const rows = useMemo(() => [...events].reverse(), [events]);

  if (error) {
    return (
      <Degraded
        code={error.code}
        message={`活动流不可用:${error.message}`}
        hint="其余页面不受影响"
        onRetry={() => void init()}
      />
    );
  }

  return (
    <section className="activity-page">
      <div className="sources-toolbar">
        <span className="label">活动</span>
        <span className="small muted">人侧与 agent 侧同流;撤销 = 执行反向操作</span>
        <span className="sources-toolbar__spacer" />
        {GROUPS.map((g) => (
          <button
            key={g.key}
            type="button"
            className={`btn btn-sm ${group === g.key ? 'btn-primary' : ''}`}
            onClick={() => setGroup(g.key)}
          >
            {g.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading-spinner">
          <div className="spinner" />
        </div>
      ) : rows.length === 0 ? (
        <p className="muted small">还没有事件:发消息、建笔记、改设置后这里会出现记录。</p>
      ) : (
        <div className="activity-list">
          {rows.map((ev) => {
            const comp = COMPENSATIONS[ev.type];
            const canUndo = comp != null && caps.has(`${comp.domain}.${comp.capability}`);
            return (
              <EventRow key={ev.seq} event={ev} canUndo={canUndo} onUndo={(e) => void undo(e)} />
            );
          })}
        </div>
      )}
    </section>
  );
}
