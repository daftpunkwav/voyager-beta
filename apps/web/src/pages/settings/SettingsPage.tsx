/** 设置页:schema 驱动动态渲染(零硬编码设置项),左侧分组右侧字段。 */

import { useEffect, useMemo, useState } from 'react';
import { Degraded } from '@/shell/Degraded';
import { SettingField } from './SettingField';
import { moduleLabel, useSettingsStore } from './settingsStore';

export function SettingsPage() {
  const { items, loading, error, load } = useSettingsStore();
  const modules = useMemo(
    () => [...new Set(items.map((i) => i.module))].sort((a, b) => a.localeCompare(b)),
    [items],
  );
  const [active, setActive] = useState<string | null>(null);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const first = modules[0];
    if (active === null && first !== undefined) setActive(first);
  }, [modules, active]);

  const visible = items.filter((i) => i.module === active);

  return (
    <section>
      <h1 className="h2">设置</h1>
      {error ? (
        <Degraded code="SETTINGS" message={error} onRetry={() => void load()} />
      ) : (
        <div className="settings-layout">
          <nav className="settings-nav" aria-label="设置分组">
            {modules.map((m) => (
              <button
                key={m}
                type="button"
                className={`nav-item ${m === active ? 'active' : ''}`}
                onClick={() => setActive(m)}
              >
                {moduleLabel(m)}
              </button>
            ))}
          </nav>
          <div className="settings-body">
            {loading && items.length === 0 ? (
              <div className="loading-spinner">
                <div className="spinner" />
              </div>
            ) : (
              visible.map((item) => <SettingField key={item.key} item={item} />)
            )}
          </div>
        </div>
      )}
    </section>
  );
}
