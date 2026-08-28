/** 团队 — Agent 与 subagent 管理(基于 agent.list_subagents / list_personas / list_tools)。
 *
 * 列出:已注册定义 / 运行中实例 / 可用人格 / 当前工具面名册。
 * 用户可在权限内新建自建 subagent(register_subagent)。
 */

import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { GlassCard } from '@/components/common/GlassCard';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { extractErrorMessage } from '@/utils/errors';

interface RunningSubagent {
  id: string;
  name: string;
  status: string;
  goal: string;
  started_ts: number;
}

interface PersonaList {
  personas: Array<{ key: string; display_name: string; style: string; default_mode: string; tool_allow: string[] | null; system_prompt: string }>;
}

interface ToolList {
  tools: Array<{ name: string; description: string }>;
}

export function TeamPage() {
  const [personas, setPersonas] = useState<PersonaList['personas']>([]);
  const [tools, setTools] = useState<ToolList['tools']>([]);
  const [running, setRunning] = useState<RunningSubagent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryTick, setRetryTick] = useState(0);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [p, t, s] = await Promise.all([
          callCapability<PersonaList['personas'] | PersonaList>('agent', 'list_personas', {}),
          callCapability<ToolList['tools'] | ToolList>('agent', 'list_tools', {}),
          callCapability<{ running?: RunningSubagent[] }>('agent', 'list_subagents', {}),
        ]);
        if (!alive) return;
        setPersonas(Array.isArray(p) ? p : p.personas ?? []);
        setTools(Array.isArray(t) ? t : t.tools ?? []);
        setRunning(s.running ?? []);
      } catch (err) {
        if (alive) setError(extractErrorMessage(err));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [retryTick]);

  if (loading) {
    return (
      <div className="team-page page-scaffold">
        <LoadingSpinner label="加载团队信息中…" />
      </div>
    );
  }
  if (error) {
    return (
      <div className="team-page page-scaffold">
        <div className="page-scaffold__state">
          <EmptyState
            title="加载失败"
            description={error}
            icon={EmptyStateIcons.team}
            onRetry={() => setRetryTick((n) => n + 1)}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="team-page page-scaffold">
      <div className="page-scaffold__body">

      <section className="team-section">
        <h2 className="h3">人格</h2>
        <div className="team-grid">
          {personas.length === 0 ? (
            <EmptyState title="暂无人格" description="后端未注册任何 Agent 人格" icon={EmptyStateIcons.team} />
          ) : (
            personas.map((p) => (
              <GlassCard key={p.key} className="persona-card">
                <div className="persona-card__head">
                  <h3 className="h3">{p.display_name}</h3>
                  <span className="chip brand">{p.key}</span>
                </div>
                <p className="muted small">{p.style}</p>
                <p className="small">默认模式:{p.default_mode}</p>
                <p className="small">
                  工具面:
                  {p.tool_allow
                    ? `${p.tool_allow.length} 项`
                    : '不裁剪(全部工具)'}
                </p>
                <details className="small">
                  <summary>系统提示词</summary>
                  <pre className="system-prompt">{p.system_prompt}</pre>
                </details>
              </GlassCard>
            ))
          )}
        </div>
      </section>

      <section className="team-section">
        <h2 className="h3">工具面名册</h2>
        <GlassCard>
          {tools.length === 0 ? (
            <EmptyState title="暂未加载" description="agent 进程尚未启动或未注册工具" icon={EmptyStateIcons.team} />
          ) : (
            <ul className="tool-list">
              {tools.map((t) => (
                <li key={t.name} className="tool-list__item">
                  <code className="mono">{t.name}</code>
                  <span className="muted small">{t.description}</span>
                </li>
              ))}
            </ul>
          )}
        </GlassCard>
      </section>

      <section className="team-section">
        <h2 className="h3">运行中 subagent</h2>
        <GlassCard>
          {running.length === 0 ? (
            <EmptyState title="暂无运行中" description="当前没有正在执行的子任务" icon={EmptyStateIcons.team} />
          ) : (
            <ul>
              {running.map((r) => (
                <li key={r.id}>
                  <strong>{r.name}</strong> — {r.goal}
                </li>
              ))}
            </ul>
          )}
        </GlassCard>
      </section>
    </div>
  </div>
);
}

export default TeamPage;

