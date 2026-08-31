/** 自建 subagent 定义列表:自己加载 list_subagents.definitions,订阅 defsEvents 刷新。 */

import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { GlassCard } from '@/components/common/GlassCard';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { extractErrorMessage } from '@/utils/errors';
import { onTeamDefsChanged } from './defsEvents';
import { patchTeamSnapshot } from './provider';
import { MODE_LABELS, NETWORK_LABELS } from './constants';
import type { PersonaItem, SubagentDef } from './types';

export function DefinitionGrid() {
  const [definitions, setDefinitions] = useState<SubagentDef[]>([]);
  const [personas, setPersonas] = useState<PersonaItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const addToast = useUIStore((s) => s.addToast);

  /** silent:造人成功后的刷新不整块转圈,避免卡片闪没导致单测/视觉抖动。 */
  const load = async (opts?: { silent?: boolean }) => {
    const silent = opts?.silent === true;
    if (!silent) {
      setLoading(true);
      setError(null);
    }
    try {
      const [s, p] = await Promise.all([
        callCapability<{ definitions?: SubagentDef[] }>('agent', 'list_subagents', {}),
        callCapability<PersonaItem[] | { personas: PersonaItem[] }>('agent', 'list_personas', {}),
      ]);
      const defsArr = s.definitions ?? [];
      const personasArr = Array.isArray(p) ? p : p.personas ?? [];
      setDefinitions(defsArr);
      setPersonas(personasArr);
      patchTeamSnapshot({ definitions: defsArr.length });
    } catch (err) {
      if (!silent) setError(extractErrorMessage(err));
      addToast({ type: 'error', message: `自建 subagent 加载失败:${extractErrorMessage(err)}` });
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    return onTeamDefsChanged(() => {
      void load({ silent: true });
    });
  }, []);

  const personaName = (key: string) => {
    if (!key) return '不绑定';
    return personas.find((p) => p.key === key)?.display_name ?? key;
  };

  if (loading) {
    return (
      <section className="team-section">
        <h2 className="h3">自建 subagent</h2>
        <LoadingSpinner label="加载自建 subagent 中…" />
      </section>
    );
  }

  if (error) {
    return (
      <section className="team-section">
        <h2 className="h3">自建 subagent</h2>
        <EmptyState
          title="自建 subagent 加载失败"
          description={error}
          icon={EmptyStateIcons.warning}
          onRetry={load}
        />
      </section>
    );
  }

  return (
    <section className="team-section">
      <h2 className="h3">自建 subagent</h2>
      <div className="team-grid">
        {definitions.length === 0 ? (
          <EmptyState
            title="还没有自建 subagent"
            description="用下方「造人」表单注册一个;注册后落盘持久,刷新页面仍在"
            icon={EmptyStateIcons.team}
          />
        ) : (
          definitions.map((d) => (
            <GlassCard key={d.name} className="persona-card">
              <div className="persona-card__head">
                <h3 className="h3">{d.name}</h3>
                <span className="chip brand">{MODE_LABELS[d.mode] ?? d.mode}</span>
              </div>
              <p className="muted small">{d.description}</p>
              <p className="small">人格:{personaName(d.persona)}</p>
              <p className="small">
                工具面:
                {d.allowed_tools ? `${d.allowed_tools.length} 项` : '不裁剪(全部工具)'}
              </p>
              <p className="small">
                轮数:
                {d.max_rounds == null && d.max_tool_calls == null
                  ? '跟随全局'
                  : `${d.max_rounds ?? '全局'} / ${d.max_tool_calls ?? '全局'}`}
              </p>
              <p className="small">网络:{NETWORK_LABELS[d.network_mode ?? ''] ?? '跟随全局'}</p>
              {d.allowed_tools && d.allowed_tools.length > 0 && (
                <details className="small">
                  <summary>工具清单</summary>
                  <pre className="system-prompt">{d.allowed_tools.join('\n')}</pre>
                </details>
              )}
            </GlassCard>
          ))
        )}
      </div>
    </section>
  );
}
