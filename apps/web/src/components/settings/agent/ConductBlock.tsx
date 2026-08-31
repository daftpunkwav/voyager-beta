import { useEffect, useState } from 'react';
import type { Settings } from '@/api/types';
import { callCapability } from '@/bridge/client';
import { GlassSelect } from '@/components/common/GlassSelect';
import { AGENT_CATALOG } from '@/constants/agentCatalog';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import {
  CONDUCT_MAX,
  DEFAULT_AGENT_ID,
  GUIDELINE_MAX,
  STYLE_KEY,
  STYLE_PRESETS,
} from './constants';
import type { SettingItem } from './types';

interface ConductBlockProps {
  settings: Settings;
  updateSettings: (data: Partial<Settings>) => Promise<unknown>;
}

/** 通用行为准则 + 说话风格 + 分 Agent 行为准则 */
export function ConductBlock({ settings, updateSettings }: ConductBlockProps) {
  const addToast = useUIStore((s) => s.addToast);
  const [activeAgentId, setActiveAgentId] = useState(DEFAULT_AGENT_ID);
  const [conductDraft, setConductDraft] = useState(settings.agent_code_of_conduct ?? '');

  const [style, setStyle] = useState<string | null>(null);
  const [styleLoadFailed, setStyleLoadFailed] = useState(false);
  const [savingStyle, setSavingStyle] = useState(false);

  const [guidelineDrafts, setGuidelineDrafts] = useState<Record<string, string>>(() => {
    const map: Record<string, string> = {};
    for (const a of AGENT_CATALOG) map[a.id] = '';
    for (const g of settings.agent_guidelines ?? []) {
      if (g.agent_id) map[g.agent_id] = g.guideline ?? '';
    }
    return map;
  });

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem>('settings', 'get_setting', { key: STYLE_KEY })
      .then((item) => {
        if (alive) setStyle(item.value ?? item.default ?? '热心');
      })
      .catch(() => {
        if (alive) setStyleLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const saveConduct = () => {
    const next = conductDraft.slice(0, CONDUCT_MAX);
    if (next === (settings.agent_code_of_conduct ?? '')) return;
    void updateSettings({ agent_code_of_conduct: next }).then(() => {
      addToast({ type: 'success', message: '通用行为准则已保存' });
    });
  };

  const saveGuideline = (agentId: string) => {
    const text = (guidelineDrafts[agentId] ?? '').slice(0, GUIDELINE_MAX);
    const prev = (settings.agent_guidelines ?? []).find((g) => g.agent_id === agentId)?.guideline ?? '';
    if (text === prev) return;
    const next = AGENT_CATALOG.map((a) => ({
      agent_id: a.id,
      guideline:
        a.id === agentId
          ? text
          : (guidelineDrafts[a.id] ??
            (settings.agent_guidelines ?? []).find((g) => g.agent_id === a.id)?.guideline ??
            ''),
    }));
    void updateSettings({ agent_guidelines: next }).then(() => {
      addToast({ type: 'success', message: `${AGENT_CATALOG.find((a) => a.id === agentId)?.name ?? agentId} 准则已保存` });
    });
  };

  const saveStyle = (value: string) => {
    const prev = style;
    setStyle(value);
    setSavingStyle(true);
    callCapability<SettingItem>('settings', 'set_setting', { key: STYLE_KEY, value })
      .then((item) => {
        setStyle(item.value ?? value);
        addToast({ type: 'success', message: '说话风格已保存，下一轮对话生效' });
      })
      .catch((err) => {
        setStyle(prev);
        addToast({ type: 'error', message: `保存风格失败：${extractErrorMessage(err)}` });
      })
      .finally(() => setSavingStyle(false));
  };

  const activeAgent = AGENT_CATALOG.find((a) => a.id === activeAgentId) ?? AGENT_CATALOG[0];

  return (
    <>
      <div className="agent-settings-block">
        <h3 className="agent-settings-subtitle">通用行为准则</h3>
        <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
          对所有 Agent 生效。例如：回答简洁、不要使用 emoji、先确认再改代码。
        </p>
        <textarea
          className="field input agent-guideline-textarea"
          rows={5}
          maxLength={CONDUCT_MAX}
          value={conductDraft}
          onChange={(e) => setConductDraft(e.target.value)}
          onBlur={saveConduct}
          placeholder="写一条所有 Agent 都应遵守的规则…"
          aria-label="通用行为准则"
        />
        <div className="agent-guideline-meta">
          <span className="muted">{conductDraft.length}/{CONDUCT_MAX}</span>
          <button type="button" className="btn btn-sm btn-ghost" onClick={saveConduct}>
            保存
          </button>
        </div>
      </div>

      <div className="agent-settings-block">
        <h3 className="agent-settings-subtitle">说话风格</h3>
        <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
          全局语气叠加层，会拼进每次对话的系统提示，与各 Agent 自带气质叠加。
        </p>
        <GlassSelect
          size="sm"
          value={style ?? ''}
          options={
            styleLoadFailed
              ? [{ value: '', label: '读取失败，请刷新重试' }]
              : [
                  ...STYLE_PRESETS.map((v) => ({ value: v, label: v })),
                  ...(style && !STYLE_PRESETS.includes(style)
                    ? [{ value: style, label: style }]
                    : []),
                ]
          }
          onChange={(v) => saveStyle(v)}
          aria-label="全局说话风格"
        />
        {savingStyle && <span className="muted" style={{ fontSize: 12, marginLeft: 8 }}>保存中…</span>}
      </div>

      <div className="agent-settings-block">
        <h3 className="agent-settings-subtitle">分 Agent 行为准则</h3>
        <p className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
          仅对选中的 Agent 生效，叠加在通用准则之上。
        </p>
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
      </div>
    </>
  );
}
