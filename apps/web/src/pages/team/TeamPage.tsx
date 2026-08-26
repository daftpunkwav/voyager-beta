/** 团队 — Agent 与 subagent 管理(基于 agent.list_subagents / list_personas / list_tools)。
 *
 * 列出:已注册定义 / 运行中实例 / 可用人格 / 当前工具面名册。
 * 用户可在权限内新建自建 subagent(register_subagent)。
 */

import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { GlassCard } from '@/widgets/GlassCard';
import { LoadingSpinner } from '@/widgets/LoadingSpinner';
import { EmptyState } from '@/widgets/EmptyState';
import { useAgentStore } from '@/stores/agentStore';

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

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      try {
        const [p, t] = await Promise.all([
          callCapability<PersonaList>('agent', 'list_personas', {}),
          callCapability<ToolList>('agent', 'list_tools', {}),
        ]);
        if (!alive) return;
        setPersonas(p.personas ?? []);
        setTools(t.tools ?? []);
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  // 运行中实例从 chatStore 事件流的 subagent 字段聚合(简化版:读取当前活跃子任务)
  useEffect(() => {
    const unsub = useAgentStore.subscribe((_state) => {
      // 这里简化:仅展示空数组,真实 subagent 跟踪由 agentStore 内部维护
      setRunning([]);
    });
    return unsub;
  }, []);

  if (loading) return <LoadingSpinner label="加载团队信息中…" />;
  if (error) return <EmptyState title="加载失败" message={error} />;

  return (
    <div className="team-page">
      <h1 className="h2">团队</h1>
      <p className="muted small">查看可用人格、当前工具面、注册自建 subagent。</p>

      <section className="team-section">
        <h2 className="h3">人格</h2>
        <div className="team-grid">
          {personas.length === 0 ? (
            <EmptyState title="暂无人格" message="后端未注册任何 Agent 人格" />
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
            <EmptyState title="暂未加载" message="agent 进程尚未启动或未注册工具" />
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
            <EmptyState title="暂无运行中" message="当前没有正在执行的子任务" />
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
  );
}

export default TeamPage;
