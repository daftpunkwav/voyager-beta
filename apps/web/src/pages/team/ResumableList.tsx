/** 可恢复/孤儿任务列表(phase-70/73,§9.17):接 list_resumable_checkpoints /
 *  resume_run / abandon_resumable_checkpoint,挂载后每 5s 轮询。
 *  resumable=false 条目(孤儿)只显示「放弃」;任务型 react 崩溃带 in_turn
 *  显示「中途中断」次要文案。与 InstanceList 同模式:自己加载、自己持
 *  state、自己 toast。 */

import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { GlassCard } from '@/components/common/GlassCard';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { extractErrorMessage } from '@/utils/errors';
import { relativeTime, statusChipClass } from './instanceFormat';
import type { ResumableCheckpoint } from './types';

/** 每隔多久轮询一次可恢复列表;abandon/cancel 后立即 reload,不等下个周期 */
const POLL_MS = 5000;

/** goal 摘要在列表里截断展示,完整内容看 title */
function truncate(text: string, max = 80): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

/** 孤儿提示:对话型 / 非 react 不可续跑,仅可放弃(phase-73 B) */
const ORPHAN_HINT = '不可续跑(对话型或其它模式),放弃可清理';

export function ResumableList() {
  const [items, setItems] = useState<ResumableCheckpoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyRunId, setBusyRunId] = useState<string | null>(null);
  const addToast = useUIStore((s) => s.addToast);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const out = await callCapability<{ items?: ResumableCheckpoint[] }>(
        'agent', 'list_resumable_checkpoints', {},
      );
      setItems(out.items ?? []);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    let alive = true;
    const timer = setInterval(() => {
      callCapability<{ items?: ResumableCheckpoint[] }>(
        'agent', 'list_resumable_checkpoints', {},
      )
        .then((out) => {
          if (alive) setItems(out.items ?? []);
        })
        .catch(() => {});
    }, POLL_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  const resume = async (item: ResumableCheckpoint) => {
    setBusyRunId(item.run_id);
    try {
      await callCapability('agent', 'resume_run', {
        run_id: item.run_id,
        continue_run: true,
      });
      addToast({ type: 'success', message: `已续跑 ${item.instance_name}。` });
      await load();
    } catch (err) {
      addToast({
        type: 'error',
        message: `续跑失败:${extractErrorMessage(err)}`,
      });
    } finally {
      setBusyRunId(null);
    }
  };

  const abandon = async (item: ResumableCheckpoint) => {
    if (!window.confirm(`放弃「${item.instance_name}」的可恢复任务?将删除其断点,不可恢复。`)) {
      return;
    }
    setBusyRunId(item.run_id);
    try {
      await callCapability('agent', 'abandon_resumable_checkpoint', {
        run_id: item.run_id,
      });
      addToast({ type: 'success', message: `已放弃 ${item.instance_name}。` });
      // 放弃后立即刷新,列表不等下个轮询周期(phase-73 E2)
      await load();
    } catch (err) {
      addToast({
        type: 'error',
        message: `放弃失败:${extractErrorMessage(err)}`,
      });
    } finally {
      setBusyRunId(null);
    }
  };

  if (loading) {
    return (
      <section className="team-section">
        <h2 className="h3">可恢复任务</h2>
        <LoadingSpinner label="加载可恢复任务中…" />
      </section>
    );
  }

  if (error) {
    return (
      <section className="team-section">
        <h2 className="h3">可恢复任务</h2>
        <EmptyState
          title="可恢复任务加载失败"
          description={error}
          icon={EmptyStateIcons.warning}
          onRetry={load}
        />
      </section>
    );
  }

  const recoverable = items.filter((i) => i.resumable !== false);
  const orphans = items.filter((i) => i.resumable === false);

  /** 单行:recoverable=true 显示「继续 + 放弃」;孤儿只显示「放弃」 */
  const row = (item: ResumableCheckpoint, orphan: boolean) => (
    <li key={item.run_id} className="inst-row">
      <div className="inst-row__head">
        <span className="inst-row__name">{item.instance_name}</span>
        <span className={`inst-row__status ${statusChipClass(item.status)}`}>
          {item.status}
        </span>
        {!orphan && (
          <button
            type="button"
            className="btn btn-sm btn-primary"
            disabled={busyRunId === item.run_id || item.status === 'running'}
            title={item.status === 'running'
              ? '任务仍在运行中,请先在实例列表急停或等待完成'
              : `续跑 ${item.instance_name}`}
            onClick={() => void resume(item)}
          >
            继续
          </button>
        )}
        <button
          type="button"
          className="btn btn-sm btn-danger"
          disabled={busyRunId === item.run_id}
          title={`放弃 ${item.instance_name}`}
          onClick={() => void abandon(item)}
        >
          放弃
        </button>
      </div>
      <span className="inst-row__goal" title={item.goal}>
        {truncate(item.goal)}
      </span>
      {item.in_turn && (
        <span className="inst-row__step" title="崩溃点在 ReAct 中途,续跑会接着已完成步骤继续">
          中途中断:崩溃在工具调用途中,续跑接着继续
        </span>
      )}
      {!item.in_turn && item.last_step && (
        <span className="inst-row__step" title={item.last_step}>
          当前:{item.last_step}
        </span>
      )}
      <span className="muted small">
        {item.run_id} · {relativeTime(item.started_ts)}
        {orphan ? ` · ${ORPHAN_HINT}` : ''}
      </span>
    </li>
  );

  return (
    <section className="team-section">
      <h2 className="h3">可恢复任务</h2>
      <GlassCard>
        {items.length === 0 ? (
          <EmptyState
            title="暂无可恢复任务"
            description="进程重启前未完成任务的任务型 subagent 会出现在这里,可继续或放弃"
            icon={EmptyStateIcons.team}
          />
        ) : (
          <>
            {recoverable.length > 0 && <ul className="inst-list">{recoverable.map((i) => row(i, false))}</ul>}
            {orphans.length > 0 && (
              <>
                <div className="muted small" style={{ margin: '10px 0 4px' }}>
                  仅可放弃的孤儿断点(对话型 / 其它模式,不可续跑)
                </div>
                <ul className="inst-list">{orphans.map((i) => row(i, true))}</ul>
              </>
            )}
          </>
        )}
      </GlassCard>
    </section>
  );
}
