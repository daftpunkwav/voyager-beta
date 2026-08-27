/** 运行实例行:goal/状态色/耗时。实例在内存(Spawner),重启即空——诚实提示。 */

import type { RunningInstance } from './teamStore';

const STATUS_LABELS: Record<string, { text: string; cls: string }> = {
  pending: { text: '排队', cls: 'inst--muted' },
  running: { text: '运行中', cls: 'inst--running' },
  waiting_input: { text: '等输入', cls: 'inst--paused' },
  paused: { text: '已暂停', cls: 'inst--paused' },
  completed: { text: '完成', cls: 'inst--done' },
  failed: { text: '失败', cls: 'inst--failed' },
  cancelled: { text: '已取消', cls: 'inst--muted' },
};

export function formatElapsed(startedTs: number, now: number): string {
  if (!startedTs) return '—';
  const s = Math.max(0, Math.round(now - startedTs));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m${s % 60}s`;
  return `${Math.floor(s / 3600)}h${Math.floor((s % 3600) / 60)}m`;
}

export function InstanceRow({ inst, now }: { inst: RunningInstance; now: number }) {
  const st = STATUS_LABELS[inst.status] ?? { text: inst.status, cls: 'inst--muted' };
  return (
    <div className="inst-row">
      <div className="inst-row__head">
        <span className={`inst-row__status ${st.cls}`}>{st.text}</span>
        <span className="inst-row__name small">{inst.name || inst.id}</span>
        <span className="small muted mono">{formatElapsed(inst.started_ts, now)}</span>
      </div>
      <div className="inst-row__goal small">{inst.goal}</div>
    </div>
  );
}
