import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { AGENT_CATALOG } from '@/constants/agentCatalog';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { DEFAULT_AGENT_ID, GUIDELINES_KEY, GUIDELINE_MAX } from './constants';
import type { SettingItem } from './types';

/** 分 Agent 行为准则(agent.guidelines):值为 { <人格结构ID>: 文本 };保存按 tab merge,空串删键 */
export function GuidelinesBlock() {
  const addToast = useUIStore((s) => s.addToast);
  const [activeAgentId, setActiveAgentId] = useState(DEFAULT_AGENT_ID);
  const [guidelineDrafts, setGuidelineDrafts] = useState<Record<string, string>>(() => {
    const map: Record<string, string> = {};
    for (const a of AGENT_CATALOG) map[a.id] = '';
    return map;
  });
  const [saved, setSaved] = useState<Record<string, string> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem<Record<string, string>>>('settings', 'get_setting', {
      key: GUIDELINES_KEY,
    })
      .then((item) => {
        if (!alive) return;
        const raw = item.value ?? item.default ?? {};
        const map: Record<string, string> = {};
        for (const a of AGENT_CATALOG) map[a.id] = typeof raw[a.id] === 'string' ? raw[a.id] : '';
        setGuidelineDrafts(map);
        setSaved(raw);
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const saveGuideline = (agentId: string) => {
    if (saved === null) return;
    const text = (guidelineDrafts[agentId] ?? '').slice(0, GUIDELINE_MAX);
    if (text === (saved[agentId] ?? '')) return;
    // merge:只更新当前 tab 的人格 id;空字符串从对象删键;其余键(含未知/自建)原样保留
    const next = { ...saved };
    if (text) next[agentId] = text;
    else delete next[agentId];
    callCapability<SettingItem<Record<string, string>>>('settings', 'set_setting', {
      key: GUIDELINES_KEY,
      value: next,
    })
      .then(() => {
        setSaved(next);
        addToast({
          type: 'success',
          message: `${AGENT_CATALOG.find((a) => a.id === agentId)?.name ?? agentId} 准则已保存`,
        });
      })
      .catch((err) => {
        const name = AGENT_CATALOG.find((a) => a.id === agentId)?.name ?? agentId;
        addToast({ type: 'error', message: `保存${name}准则失败：${extractErrorMessage(err)}` });
      });
  };

  const activeAgent = AGENT_CATALOG.find((a) => a.id === activeAgentId) ?? AGENT_CATALOG[0];

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">分 Agent 行为准则</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
        仅对选中的 Agent 生效，叠加在通用准则之上。
      </p>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>读取失败请刷新。</p>
      ) : (
        <>
          <div className="agent-guideline-tabs" role="tablist" aria-label="选择 Agent">
            {AGENT_CATALOG.map((a) => (
              <button
                key={a.id}
                type="button"
                role="tab"
                aria-selected={a.id === activeAgentId}
                className={`agent-guideline-tab ${a.id === activeAgentId ? 'active' : ''}`}
                onClick={() => setActiveAgentId(a.id)}
              >
                {a.name}
              </button>
            ))}
          </div>
          {activeAgent && (
            <div className="agent-guideline-panel">
              <div className="agent-guideline-panel__head">
                <strong>{activeAgent.name}</strong>
                <span className="muted">{activeAgent.tagline}</span>
              </div>
              <textarea
                className="field input agent-guideline-textarea"
                rows={4}
                maxLength={GUIDELINE_MAX}
                value={guidelineDrafts[activeAgent.id] ?? ''}
                onChange={(e) =>
                  setGuidelineDrafts((prev) => ({ ...prev, [activeAgent.id]: e.target.value }))
                }
                onBlur={() => saveGuideline(activeAgent.id)}
                placeholder={`为 ${activeAgent.name} 写专属规则…`}
                aria-label={`${activeAgent.name} 行为准则`}
              />
              <div className="agent-guideline-meta">
                <span className="muted">
                  {(guidelineDrafts[activeAgent.id] ?? '').length}/{GUIDELINE_MAX}
                </span>
                <button
                  type="button"
                  className="btn btn-sm btn-ghost"
                  onClick={() => saveGuideline(activeAgent.id)}
                >
                  保存
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
