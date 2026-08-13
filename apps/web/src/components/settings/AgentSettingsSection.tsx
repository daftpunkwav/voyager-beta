import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getApi } from '@/api/client';
import type { Settings } from '@/api/types';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { AGENT_CATALOG } from '@/constants/agentCatalog';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';

const CONDUCT_MAX = 4000;
const GUIDELINE_MAX = 2000;

interface AgentSettingsSectionProps {
  settings: Settings;
  updateSettings: (data: Partial<Settings>) => Promise<unknown>;
}

export function AgentSettingsSection({ settings, updateSettings }: AgentSettingsSectionProps) {
  const addToast = useUIStore((s) => s.addToast);
  const qc = useQueryClient();
  const [clearOpen, setClearOpen] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [activeAgentId, setActiveAgentId] = useState(AGENT_CATALOG[0]?.id ?? 'hub');
  const [conductDraft, setConductDraft] = useState(settings.agent_code_of_conduct ?? '');
  const [guidelineDrafts, setGuidelineDrafts] = useState<Record<string, string>>(() => {
    const map: Record<string, string> = {};
    for (const a of AGENT_CATALOG) map[a.id] = '';
    for (const g of settings.agent_guidelines ?? []) {
      if (g.agent_id) map[g.agent_id] = g.guideline ?? '';
    }
    return map;
  });

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

  const handleClearMemory = async () => {
    setClearing(true);
    try {
      await getApi().clearUserMemory();
      await qc.invalidateQueries({ queryKey: ['userProfile'] });
      addToast({ type: 'success', message: '已清除 Agent 关于你的画像记忆' });
    } catch (err) {
      const detail = extractErrorMessage(err);
      addToast({
        type: 'error',
        message: detail && detail !== '请求失败' ? `清除记忆失败：${detail}` : '清除记忆失败',
      });
    } finally {
      setClearing(false);
      setClearOpen(false);
    }
  };

  const activeAgent = AGENT_CATALOG.find((a) => a.id === activeAgentId) ?? AGENT_CATALOG[0];

  return (
    <>
      <section className="settings-section glass-card glass-card--overview-outer">
        <h2>Agent</h2>
        <p className="section-desc">行为准则与记忆管理。准则会注入每次对话的系统提示，所有 Agent 必须遵守。</p>

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

        <div className="agent-settings-block agent-settings-block--danger">
          <h3 className="agent-settings-subtitle">清除记忆</h3>
          <p className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
            清除 Agent 关于你的画像记忆（技术栈、学习目标、偏好、长期/短期记忆摘要等）。
            <strong> 不会删除对话历史、项目或笔记。</strong>
          </p>
          <button
            type="button"
            className="btn btn-sm"
            style={{ color: 'var(--danger, #ff6b6b)', borderColor: 'var(--danger, #ff6b6b)' }}
            onClick={() => setClearOpen(true)}
            disabled={clearing}
            data-testid="clear-memory-btn"
          >
            清除 Agent 记忆
          </button>
        </div>
      </section>

      <ConfirmDialog
        open={clearOpen}
        title="清除 Agent 记忆"
        message="确定让 Agent 忘记关于你的所有画像信息？对话历史、项目库与笔记会保留，此操作不可撤销。"
        danger
        onConfirm={() => void handleClearMemory()}
        onCancel={() => setClearOpen(false)}
      />
    </>
  );
}
