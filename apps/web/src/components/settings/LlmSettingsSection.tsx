import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { callCapability, ServiceError } from '@/bridge/client';
import type { LlmProvider } from '@/api/types';
import { LlmProviderAdd } from './llm/LlmProviderAdd';
import { LlmAgentOverrides } from './llm/LlmAgentOverrides';
import { LlmProviderDetail } from './llm/LlmProviderDetail';
import { LlmProviderList } from './llm/LlmProviderList';
import { Degraded } from '@/shell/Degraded';

/** llm.test_connection 返回形态(ok/error/latency_ms/model;无 reply/success) */
export interface LlmTestOutcome {
  ok: boolean;
  latency_ms?: number;
  model?: string;
  error?: string;
}

const DEFAULT_PROVIDER_KEY = 'llm.default_provider';

/** 设置 → LLM:llm 服务客户端。
 *
 * 数据层全部走 llm.* 能力(列表/增删改/密钥/连通测试)+ settings.set_setting
 * (llm.default_provider)。不再读写旧 settings blob 的 llm_providers——后端
 * 真相在 llm store 与 platform/secrets,key 永不回传,页面只读 has_api_key。
 */
export function LlmSettingsSection() {
  const [providers, setProviders] = useState<LlmProvider[]>([]);
  const [defaultId, setDefaultId] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);
  const [adding, setAdding] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<LlmTestOutcome | null>(null);

  const reload = useCallback(async () => {
    setError(null);
    try {
      const [list, defItem] = await Promise.all([
        callCapability<LlmProvider[]>('llm', 'list_providers'),
        callCapability<{ value?: unknown }>('settings', 'get_setting', {
          key: DEFAULT_PROVIDER_KEY,
        }),
      ]);
      setProviders(list);
      setDefaultId(String(defItem?.value ?? ''));
      setLoading(false);
      return list;
    } catch (err) {
      const e = err as ServiceError;
      setError({ code: e.code, message: e.message });
      setLoading(false);
      return [];
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  // 选中项跟随列表:优先保持当前选择,否则取默认/第一个
  useEffect(() => {
    if (selectedId && providers.some((p) => p.id === selectedId)) return;
    setSelectedId(
      providers.find((p) => p.id === defaultId)?.id ?? providers[0]?.id ?? null,
    );
  }, [providers, defaultId, selectedId]);

  if (loading) {
    return <p className="muted small">加载提供商中…</p>;
  }
  if (error) {
    return <Degraded code={error.code} message={error.message} onRetry={() => void reload()} />;
  }

  const selected = providers.find((p) => p.id === selectedId) ?? null;
  const anyUsable = providers.some((p) => p.enabled && p.has_api_key);

  /** 元数据补丁:update_provider(不含 key;格式枚举仅 chat/anthropic) */
  const patchProvider = (
    id: string,
    patch: Partial<Pick<LlmProvider, 'display_name' | 'base_url' | 'api_format' | 'models' | 'default_model' | 'enabled'>>,
  ) =>
    callCapability('llm', 'update_provider', { provider_id: id, ...patch }).then(() =>
      reload(),
    );

  const saveKey = async (id: string, apiKey: string) => {
    await callCapability('llm', 'set_api_key', { provider_id: id, api_key: apiKey });
    await reload();
  };

  const testConnection = async (id: string, model: string) => {
    setIsTesting(true);
    setTestResult(null);
    try {
      const out = await callCapability<LlmTestOutcome>('llm', 'test_connection', {
        provider_id: id,
        model,
      });
      setTestResult(out);
    } catch (err) {
      // 能力层报错(如未配 key)直接展示后端错误,不造 success/reply 字段
      const e = err as ServiceError;
      setTestResult({ ok: false, error: e.hint ? `${e.message}(${e.hint})` : e.message });
    } finally {
      setIsTesting(false);
    }
  };

  const removeProvider = async (id: string) => {
    await callCapability('llm', 'remove_provider', { provider_id: id });
    // 删除的是默认提供商时清掉设置项,避免 ServiceLLM 解析到已删除 id(它会自动回退,但设置项应保持诚实)
    if (defaultId === id) {
      await callCapability('settings', 'set_setting', {
        key: DEFAULT_PROVIDER_KEY,
        value: '',
      });
      setDefaultId('');
    }
    await reload();
  };

  const setDefault = async (id: string) => {
    await callCapability('settings', 'set_setting', {
      key: DEFAULT_PROVIDER_KEY,
      value: id,
    });
    setDefaultId(id);
  };

  return (
    <div className="llm-settings">
      {!anyUsable && (
        <div className="alert alert-warning">
          <strong>未配置</strong> — 请为至少一个供应商填写 API Key 并测试；未配置时
          Agent 将使用规则降级模式。
        </div>
      )}

      <p className="section-desc" style={{ marginTop: 0 }}>
        多供应商可并存；设为默认的供应商就是对话实际调用的那家。
        <Link to="/usage" style={{ marginLeft: 8 }}>
          查看 LLM 用量 →
        </Link>
      </p>

      <div className="llm-multi-layout">
        <LlmProviderList
          providers={providers}
          selectedId={selected?.id ?? null}
          defaultProviderId={defaultId}
          onSelect={setSelectedId}
          onAdd={() => setAdding((v) => !v)}
        />
        <div>
          {adding ? (
            <LlmProviderAdd
              onDone={async (id) => {
                setAdding(false);
                await reload();
                if (id) setSelectedId(id);
              }}
            />
          ) : null}
          {selected ? (
            <LlmProviderDetail
              provider={selected}
              isDefault={selected.id === defaultId}
              isTesting={isTesting}
              testResult={testResult}
              onPatch={(patch) => patchProvider(selected.id, patch)}
              onSaveKey={(key) => saveKey(selected.id, key)}
              onSetDefault={() => void setDefault(selected.id)}
              onDelete={() => void removeProvider(selected.id)}
              onTest={(model) => void testConnection(selected.id, model)}
            />
          ) : (
            <div className="glass-card glass-card--overview-inner" style={{ padding: 24 }}>
              {providers.length === 0
                ? '尚无提供商;从内置目录新增一个开始。'
                : '请选择左侧供应商'}
            </div>
          )}
        </div>
      </div>

      <LlmAgentOverrides
        providers={providers}
        defaultProviderId={defaultId}
      />
    </div>
  );
}
