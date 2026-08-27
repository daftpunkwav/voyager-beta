/** LLM 提供商区块:卡片列表 + 新增编辑器入口。 */

import { useCallback, useEffect, useState } from 'react';
import { callCapability, ServiceError } from '@/bridge/client';
import { Degraded } from '@/shell/Degraded';
import { ProviderCard } from './ProviderCard';
import { ProviderEditor } from './ProviderEditor';

export interface Provider {
  id: string;
  display_name: string;
  preset_id: string;
  base_url: string;
  api_format: 'chat' | 'anthropic';
  models: string[];
  default_model: string;
  enabled: boolean;
  custom: boolean;
  has_api_key: boolean;
}

export function ProviderSection() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);
  const [adding, setAdding] = useState(false);

  const reload = useCallback(async () => {
    setError(null);
    try {
      setProviders(await callCapability<Provider[]>('llm', 'list_providers'));
    } catch (err) {
      const e = err as ServiceError;
      setError({ code: e.code, message: e.message });
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  if (error) {
    return <Degraded code={error.code} message={error.message} onRetry={() => void reload()} />;
  }

  return (
    <div className="provider-grid">
      <div>
        <button type="button" className="btn btn-primary" onClick={() => setAdding((v) => !v)}>
          {adding ? '收起' : '新增提供商'}
        </button>
      </div>
      {adding ? (
        <ProviderEditor
          onDone={() => {
            setAdding(false);
            void reload();
          }}
        />
      ) : null}
      {providers.length === 0 && !adding ? (
        <p className="muted small">尚无提供商;从内置目录新增一个开始。</p>
      ) : null}
      {providers.map((p) => (
        <ProviderCard key={p.id} provider={p} onChanged={reload} />
      ))}
    </div>
  );
}
