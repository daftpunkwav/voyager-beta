/** subagent 实例列表:自己加载 list_subagents.running,挂载后每 5s 轮询,原样急停。 */

import { useEffect, useState } from 'react';
import { callCapability, ServiceError } from '@/bridge/client';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { GlassCard } from '@/components/common/GlassCard';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { extractErrorMessage } from '@/utils/errors';
import { patchTeamSnapshot } from './provider';
import type { RunningSubagent } from './types';

/** started_ts 是秒级 unix 时间戳(agent/runtime/state.py time.time()) */
function relativeTime(ts: number): string {
  if (!ts) return '';
  const diff = Math.max(0, Date.now() / 1000 - ts);
  if (diff < 60) return '刚刚';
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  return `${Math.floor(diff / 86400)} 天前`;
}

/** 实例状态 → 状态色片(shell.css .inst--*) */
function statusChipClass(status: string): string {
  switch (status) {
    case 'running':
      return 'inst--running';
    case 'completed':
      return 'inst--done';
    case 'failed':
      return 'inst--failed';
    case 'paused':
      return 'inst--paused';
    default:
      return 'inst--muted';
  }
}

export function InstanceList() {
  const [instances, setInstances] = useState<RunningSubagent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const addToast = useUIStore((s) => s.addToast);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const s = await callCapability<{ running?: RunningSubagent[] }>('agent', 'list_subagents', {});
      const runningArr = s.running ?? [];
      setInstances(runningArr);
      patchTeamSnapshot({ running: runningArr.filter((r) => r.status === 'running').length });
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
      callCapability<{ running?: RunningSubagent[] }>('agent', 'list_subagents', {})
        .then((s) => {
          if (!alive) return;
          const runningArr = s.running ?? [];
          setInstances(runningArr);
          patchTeamSnapshot({ running: runningArr.filter((r) => r.status === 'running').length });
        })
        .catch(() => {});
    }, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  const stopRun = async (r: RunningSubagent) => {
    const isChat = r.id === 'chat' || r.name === 'chat';
    try {
      await callCapability('agent', 'cancel_run', { id_or_name: r.id });
      if (isChat) useChatStore.setState({ thinking: false });
      addToast({
        type: 'success',
        message: isChat ? '已中断对话主实例。' : `已中断 ${r.name}。`,
      });
      setInstances((prev) => prev.filter((x) => x.id !== r.id && x.name !== r.id));
    } catch (err) {
      const notFound = err instanceof ServiceError && err.code.includes('NOT_FOUND');
      if (notFound) {
        setInstances((prev) => prev.filter((x) => x.id !== r.id && x.name !== r.id));
      }
      addToast({
        type: 'error',
        message: notFound ? `${r.name} 已不在运行。` : `急停失败:${extractErrorMessage(err)}`,
      });
    }
  };

  if (loading) {
    return (
      <section className="team-section">
        <h2 className="h3">subagent 实例</h2>
        <LoadingSpinner label="加载实例中…" />
      </section>
    );
  }

  if (error) {
    return (
      <section className="team-section">
        <h2 className="h3">subagent 实例</h2>
        <EmptyState
          title="实例加载失败"
          description={error}
          icon={EmptyStateIcons.warning}
          onRetry={load}
        />
      </section>
    );
  }

  return (
    <section className="team-section">
      <h2 className="h3">subagent 实例</h2>
      <GlassCard>
        {instances.length === 0 ? (
          <EmptyState
            title="暂无实例"
            description="subagent 派生后出现在这里;对话主实例 chat 在对话进行时存在"
            icon={EmptyStateIcons.team}
          />
        ) : (
          <ul className="inst-list">
            {instances.map((r) => (
              <li key={r.id} className="inst-row">
                <div className="inst-row__head">
                  <span className="inst-row__name">{r.name}</span>
                  <span className={`inst-row__status ${statusChipClass(r.status)}`}>{r.status}</span>
                  {r.status === 'running' && (
                    <button
                      type="button"
                      className="btn btn-sm btn-danger"
                      title={r.name === 'chat' ? '急停将中断当前对话' : `急停 ${r.name}`}
                      onClick={() => void stopRun(r)}
                    >
                      急停
                    </button>
                  )}
                </div>
                <span className="inst-row__goal">{r.goal}</span>
                {r.last_step && (
                  <span className="inst-row__step" title={r.last_step}>
                    当前:{r.last_step}
                  </span>
                )}
                <span className="muted small">
                  {r.id} · {relativeTime(r.started_ts)}
                  {r.name === 'chat' || r.id === 'chat'
                    ? ' · 对话主实例,急停会中断当前对话'
                    : ''}
                </span>
              </li>
            ))}
          </ul>
        )}
      </GlassCard>
    </section>
  );
}
