/** 设置页:schema 驱动动态渲染(零硬编码设置项),左侧分组右侧字段。
 * ?module=<name> 深链直开对应分组(团队页权限矩阵等处跳转入口)。 */

import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Degraded } from '@/shell/Degraded';
import { SettingField } from './SettingField';
import { moduleLabel, useSettingsStore } from './settingsStore';
import { ProviderSection } from './ProviderSection';

export function SettingsPage() {
  const { items, loading, error, load } = useSettingsStore();
  const [params] = useSearchParams();
  const modules = useMemo(
    () => [...new Set(items.map((i) => i.module))].sort((a, b) => a.localeCompare(b)),
    [items],
  );
  const [active, setActive] = useState<string | null>(null);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (active !== null) return;
    const target = params.get('module');
    if (target && modules.includes(target)) {
      setActive(target); // 深链优先于默认首组
      return;
    }
    const first = modules[0];
    if (first !== undefined) setActive(first);
  }, [modules, active, params]);

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
            <button
              type="button"
              className={`nav-item ${active === 'providers' ? 'active' : ''}`}
              onClick={() => setActive('providers')}
            >
              LLM 提供商
            </button>
          </nav>
          <div className="settings-body">
            {loading && items.length === 0 ? (
              <div className="loading-spinner">
                <div className="spinner" />
              </div>
            ) : active === 'providers' ? (
              <ProviderSection />
            ) : (
              visible.map((item) => <SettingField key={item.key} item={item} />)
            )}
          </div>
        </div>
      )}
    </section>
  );
}
