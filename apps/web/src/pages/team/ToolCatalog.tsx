/** 工具面名册:自己加载 list_tools。 */

import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { GlassCard } from '@/components/common/GlassCard';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { extractErrorMessage } from '@/utils/errors';
import type { ToolItem } from './types';

export function ToolCatalog() {
  const [tools, setTools] = useState<ToolItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const addToast = useUIStore((s) => s.addToast);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await callCapability<ToolItem[] | { tools: ToolItem[] }>('agent', 'list_tools', {});
      const arr = Array.isArray(res) ? res : res.tools ?? [];
      setTools(arr);
    } catch (err) {
      setError(extractErrorMessage(err));
      addToast({ type: 'error', message: `工具面加载失败:${extractErrorMessage(err)}` });
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
        <h2 className="h3">工具面名册</h2>
        <LoadingSpinner label="加载工具面中…" />
      </section>
    );
  }

  if (error) {
    return (
      <section className="team-section">
        <h2 className="h3">工具面名册</h2>
        <EmptyState
          title="工具面加载失败"
          description={error}
          icon={EmptyStateIcons.warning}
          onRetry={load}
        />
      </section>
    );
  }

  return (
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
  );
}
