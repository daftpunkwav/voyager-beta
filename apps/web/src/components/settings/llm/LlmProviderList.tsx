import type { LlmProviderConfig } from '@/api/types';
import { GLASS_INNER } from '@/constants/glassTokens';

interface LlmProviderListProps {
  providers: LlmProviderConfig[];
  selectedId: string | null;
  defaultProviderId: string | null;
  onSelect: (id: string) => void;
  onAdd: () => void;
}

export function LlmProviderList({
  providers,
  selectedId,
  defaultProviderId,
  onSelect,
  onAdd,
}: LlmProviderListProps) {
  return (
    <aside className="llm-provider-rail glass-card glass-card--overview-inner">
      <div className="llm-provider-rail-title">供应商</div>
      <ul className="llm-provider-list">
        {providers.map((p) => {
          const active = p.id === selectedId;
          const isDefault = p.id === defaultProviderId;
          return (
            <li key={p.id}>
              <button
                type="button"
                className={`llm-provider-item ${active ? 'is-active' : ''} ${GLASS_INNER}`}
                onClick={() => onSelect(p.id)}
              >
                <span className="llm-provider-item-name">
                  {p.display_name || p.preset_id}
                  {isDefault ? <span className="llm-provider-default-tag">默认</span> : null}
                </span>
                <span
                  className={`llm-provider-status ${p.enabled && p.configured ? 'is-on' : ''}`}
                  title={p.enabled ? (p.configured ? '已配置' : '未配置 Key') : '已禁用'}
                />
              </button>
            </li>
          );
        })}
      </ul>
      <button type="button" className={`btn btn-sm llm-provider-add ${GLASS_INNER}`} onClick={onAdd}>
        + 添加供应商
      </button>
    </aside>
  );
}
