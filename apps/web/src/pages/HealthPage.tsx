/** 服务状态页(本阶段唯一调试页):/health 聚合 + 能力直调面板(链路验收用)。 */

import { useCallback, useEffect, useState } from 'react';
import { callCapability, ServiceError } from '@/bridge/client';
import { Degraded } from '@/shell/Degraded';

interface HealthBody {
  status: string;
  services: Record<string, { status: string; detail?: Record<string, unknown> }>;
}

export function HealthPage() {
  const [health, setHealth] = useState<HealthBody | null>(null);
  const [error, setError] = useState<{ code: string; message: string; hint: string } | null>(
    null,
  );

  const refresh = useCallback(() => {
    setError(null);
    fetch('/health')
      .then((r) => r.json())
      .then(setHealth)
      .catch(() =>
        setError({ code: 'NETWORK', message: '后端不可达', hint: '请确认后端已启动(python deploy/dev.py)' }),
      );
  }, []);

  useEffect(refresh, [refresh]);

  return (
    <section>
      <h1 className="h2">服务状态</h1>
      <p className="muted small">聚合健康探测;能力直调面板验证 web → gateway → 服务链路。</p>

      {error ? (
        <Degraded code={error.code} message={error.message} hint={error.hint} onRetry={refresh} />
      ) : health ? (
        <div className="health-grid" style={{ margin: '16px 0 32px' }}>
          {Object.entries(health.services).map(([domain, s]) => (
            <div className="health-card" key={domain}>
              <div className="mono small" style={{ fontWeight: 600 }}>{domain}</div>
              <div className={`health-card__status health-card__status--${s.status}`}>
                {s.status === 'up' ? '●' : '●'} {s.status}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="loading-spinner">
          <div className="spinner" />
        </div>
      )}

      <h2 className="h3">能力直调</h2>
      <CapabilityDebugger />
    </section>
  );
}

function CapabilityDebugger() {
  const [domain, setDomain] = useState('notes');
  const [name, setName] = useState('create_note');
  const [argsText, setArgsText] = useState('{\n  "title": "链路测试"\n}');
  const [result, setResult] = useState<string>('');
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    setResult('');
    try {
      let args: Record<string, unknown>;
      try {
        args = JSON.parse(argsText || '{}');
      } catch {
        throw new ServiceError('INVALID_JSON', '入参不是合法 JSON');
      }
      const out = await callCapability(domain, name, args);
      setResult(JSON.stringify(out, null, 2));
    } catch (err) {
      const e = err as ServiceError;
      setResult(`[${e.code}] ${e.message}${e.hint ? `\n提示: ${e.hint}` : ''}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="debug-panel" style={{ marginTop: 12 }}>
      <div style={{ display: 'flex', gap: 8 }}>
        <input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="domain" />
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="capability" />
      </div>
      <textarea
        rows={5}
        value={argsText}
        onChange={(e) => setArgsText(e.target.value)}
        placeholder="JSON 入参"
      />
      <div>
        <button type="button" className="btn btn-primary" onClick={run} disabled={busy}>
          {busy ? '执行中…' : '调用'}
        </button>
      </div>
      {result ? <pre>{result}</pre> : null}
    </div>
  );
}
