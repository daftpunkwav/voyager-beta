/** 人格预设网格:自己加载 list_personas、自己 toast。 */

import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { GlassCard } from '@/components/common/GlassCard';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { extractErrorMessage } from '@/utils/errors';
import { patchTeamSnapshot } from './provider';
import type { PersonaItem } from './types';

export function PersonaGrid() {
  const [personas, setPersonas] = useState<PersonaItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const addToast = useUIStore((s) => s.addToast);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await callCapability<PersonaItem[] | { personas: PersonaItem[] }>(
        'agent',
        'list_personas',
        {},
      );
      const arr = Array.isArray(res) ? res : res.personas ?? [];
      setPersonas(arr);
      patchTeamSnapshot({ personas: arr.length });
    } catch (err) {
      setError(extractErrorMessage(err));
      addToast({ type: 'error', message: `人格加载失败:${extractErrorMessage(err)}` });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  if (loading) {
    return (
      <section className="team-section">
        <h2 className="h3">人格</h2>
        <LoadingSpinner label="加载人格中…" />
      </section>
    );
  }

  if (error) {
    return (
      <section className="team-section">
        <h2 className="h3">人格</h2>
        <EmptyState
          title="人格加载失败"
          description={error}
          icon={EmptyStateIcons.warning}
          onRetry={load}
        />
      </section>
    );
  }

  return (
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
                {p.tool_allow ? `${p.tool_allow.length} 项` : '不裁剪(全部工具)'}
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
  );
}
