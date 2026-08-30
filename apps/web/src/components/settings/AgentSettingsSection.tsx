import { useEffect, useState } from 'react';
import type { Settings } from '@/api/types';
import { callCapability } from '@/bridge/client';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { GlassSelect } from '@/components/common/GlassSelect';
import { AGENT_CATALOG } from '@/constants/agentCatalog';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';

const CONDUCT_MAX = 4000;
const GUIDELINE_MAX = 2000;

/** 全局说话风格预设(agent.style,自由字符串的常用取值;叠加在每个人格气质之上) */
const STYLE_PRESETS = ['热心', '毒舌', '严谨', '简洁', '幽默', '专业'];
const STYLE_KEY = 'agent.style';

/** 情节记忆保留天数(agent.memory.retention_days;范围与 SettingDef 一致) */
const RETENTION_KEY = 'agent.memory.retention_days';
const RETENTION_MAX = 3650;

/** agent.get_memory 返回形状(与 agent/capabilities.py 对齐,前端不猜字段) */
interface SettingItem<T = string> {
  value?: T;
  default?: T;
}
interface ProfileItem {
  key: string;
  value: unknown;
}
interface EpisodicEntry {
  id: number;
  ts: number;
  kind: string;
  summary: string;
}
interface SemanticFact {
  id: number;
  ts: number;
  subject: string;
  relation: string;
  object: string;
}
interface MemorySnapshot {
  profile: { summary: string; items: ProfileItem[] };
  episodic: { recent: EpisodicEntry[]; shown: number };
  semantic: { recent: SemanticFact[]; shown: number };
  working: { size: number };
  retention_days: number;
  purged_episodic: number;
}
type MemoryZone = 'profile' | 'episodic' | 'semantic' | 'working' | 'all';

/** 记忆区中文名(确认框标题与 toast 用) */
const ZONE_LABELS: Record<MemoryZone, string> = {
  profile: '用户画像',
  episodic: '情节记忆',
  semantic: '语义记忆',
  working: '工作记忆',
  all: '全部记忆',
};

/** 分区清空确认文案:写清"对话时间线/笔记/项目保留" */
const CONFIRM_MESSAGES: Record<Exclude<MemoryZone, 'working'>, string> = {
  all: '确定清空 Agent 的全部记忆（用户画像、情节、语义、工作）？对话时间线、笔记与项目会保留，此操作不可恢复。',
  profile: '确定清空用户画像？Agent 将忘记你的偏好与背景。对话时间线、笔记与项目会保留，此操作不可恢复。',
  episodic: '确定清空情节记忆（决策与事件留痕）？对话时间线、笔记与项目会保留，此操作不可恢复。',
  semantic: '确定清空语义记忆（事实三元组）？对话时间线、笔记与项目会保留，此操作不可恢复。',
};

/** 情节 ts 是 unix 秒,转本地时间展示 */
const fmtTs = (ts: number) => new Date(ts * 1000).toLocaleString();

/** 画像值非字符串(数字/对象)时以 JSON 展示,避免 "[object Object]" */
const fmtValue = (value: unknown) =>
  typeof value === 'string' ? value : JSON.stringify(value) ?? '';

interface AgentSettingsSectionProps {
  settings: Settings;
  updateSettings: (data: Partial<Settings>) => Promise<unknown>;
}

export function AgentSettingsSection({ settings, updateSettings }: AgentSettingsSectionProps) {
  const addToast = useUIStore((s) => s.addToast);
  const [activeAgentId, setActiveAgentId] = useState(AGENT_CATALOG[0]?.id ?? 'orchestrator');
  const [conductDraft, setConductDraft] = useState(settings.agent_code_of_conduct ?? '');
  const [style, setStyle] = useState<string | null>(null); // null = 未加载
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

  // 记忆快照(null = 加载中;loadFailed 时不整页 EmptyState,准则/风格区仍可用)
  const [mem, setMem] = useState<MemorySnapshot | null>(null);
  const [memLoadFailed, setMemLoadFailed] = useState(false);
  // 画像新增表单
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  // 保留天数输入草稿('' = 未加载)
  const [retention, setRetention] = useState('');
  // 待确认的清空区(working 进程内即空,不弹确认)
  const [confirmZone, setConfirmZone] = useState<MemoryZone | null>(null);
  const [clearing, setClearing] = useState(false);
  const [busyZone, setBusyZone] = useState<MemoryZone | null>(null);

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

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem>('settings', 'get_setting', { key: STYLE_KEY })
      .then((item) => {
        if (alive) setStyle(item.value ?? item.default ?? '热心');
      })
      .catch(() => {
        if (alive) setStyleLoadFailed(true);
      });
    // 记忆快照:一次取齐画像/情节/语义/工作与保留天数
    callCapability<MemorySnapshot>('agent', 'get_memory', {})
      .then((snap) => {
        if (!alive) return;
        setMem(snap);
        // get_setting 未先返回时用快照值兜底填输入框
        setRetention((prev) => (prev === '' ? String(snap.retention_days) : prev));
      })
      .catch((err) => {
        if (!alive) return;
        setMemLoadFailed(true);
        addToast({ type: 'error', message: `记忆快照加载失败：${extractErrorMessage(err)}` });
      });
    callCapability<SettingItem<number>>('settings', 'get_setting', { key: RETENTION_KEY })
      .then((item) => {
        if (alive) setRetention(String(item.value ?? item.default ?? 0));
      })
      .catch(() => {
        /* 保留天数读取失败由快照值兜底,不拦记忆区 */
      });
    return () => {
      alive = false;
    };
  }, []);

  const saveStyle = (value: string) => {
    const prev = style;
    setStyle(value); // 乐观更新,失败回滚
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

  /** 重新拉记忆快照(成功静默;失败 toast,不打断页面) */
  const reloadMemory = () =>
    callCapability<MemorySnapshot>('agent', 'get_memory', {})
      .then((snap) => setMem(snap))
      .catch((err) => {
        addToast({ type: 'error', message: `记忆快照刷新失败：${extractErrorMessage(err)}` });
      });

  const handleAddProfile = async () => {
    const key = newKey.trim();
    if (!key) {
      addToast({ type: 'warning', message: '请先填写画像键' });
      return;
    }
    try {
      await callCapability('agent', 'set_profile', { key, value: newValue });
      setNewKey('');
      setNewValue('');
      addToast({ type: 'success', message: '画像键值已保存' });
      await reloadMemory();
    } catch (err) {
      addToast({ type: 'error', message: `保存画像失败：${extractErrorMessage(err)}` });
    }
  };

  const handleDeleteProfile = async (key: string) => {
    try {
      await callCapability('agent', 'delete_profile', { key });
      addToast({ type: 'success', message: `已删除画像键「${key}」` });
      await reloadMemory();
    } catch (err) {
      addToast({ type: 'error', message: `删除画像失败：${extractErrorMessage(err)}` });
    }
  };

  /** 工作记忆进程内即空,直接清不弹确认 */
  const handleClearWorking = async () => {
    setBusyZone('working');
    try {
      await callCapability('agent', 'clear_memory', { zone: 'working' });
      addToast({ type: 'success', message: '工作记忆已清空' });
      await reloadMemory();
    } catch (err) {
      addToast({ type: 'error', message: `清空失败：${extractErrorMessage(err)}` });
    } finally {
      setBusyZone(null);
    }
  };

  const handleClearMemory = async () => {
    const zone = confirmZone;
    if (!zone || zone === 'working') return;
    setClearing(true);
    try {
      await callCapability('agent', 'clear_memory', { zone });
      addToast({ type: 'success', message: `已清空${ZONE_LABELS[zone]}` });
      await reloadMemory();
    } catch (err) {
      addToast({ type: 'error', message: `清空失败：${extractErrorMessage(err)}` });
    } finally {
      setClearing(false);
      setConfirmZone(null);
    }
  };

  const saveRetention = () => {
    const n = Number(retention);
    if (!Number.isInteger(n) || n < 0 || n > RETENTION_MAX) {
      addToast({ type: 'warning', message: `保留天数须为 0–${RETENTION_MAX} 的整数，0 表示交给 Agent 管理` });
      return;
    }
    callCapability<SettingItem<number>>('settings', 'set_setting', { key: RETENTION_KEY, value: n })
      .then(() => {
        addToast({
          type: 'success',
          message:
            n > 0
              ? `情节记忆保留 ${n} 天，打开本页时清理更早情节`
              : '已交给 Agent 管理，不再按天清理',
        });
      })
      .catch((err) => {
        addToast({ type: 'error', message: `保存保留天数失败：${extractErrorMessage(err)}` });
      });
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
                    // 后端存了预设之外的值(如 agent 自己改过)时原样展示,避免显示错位
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

        <div className="agent-settings-block">
          <h3 className="agent-settings-subtitle">记忆</h3>
          <p className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
            Agent 的四类记忆。画像摘要会注入每次对话的系统提示；清空只影响记忆，
            对话时间线、笔记与项目保留。
          </p>
          {memLoadFailed && (
            <p className="muted" style={{ fontSize: 12 }}>
              记忆快照加载失败，上方风格与准则不受影响；请刷新重试。
            </p>
          )}
          {!memLoadFailed && !mem && (
            <p className="muted" style={{ fontSize: 12 }}>记忆快照加载中…</p>
          )}
          {mem && (
            <>
              <div className="memory-subhead">画像摘要</div>
              <pre className="memory-summary">{mem.profile.summary}</pre>

              <div className="memory-subhead">画像键值</div>
              {mem.profile.items.length === 0 ? (
                <p className="muted" style={{ fontSize: 12 }}>暂无画像键值。</p>
              ) : (
                <ul className="memory-kv-list">
                  {mem.profile.items.map((item) => (
                    <li key={item.key} className="memory-kv-row">
                      <span className="memory-kv-key">{item.key}</span>
                      <span className="memory-kv-value">{fmtValue(item.value)}</span>
                      <button
                        type="button"
                        className="btn btn-sm btn-ghost"
                        onClick={() => void handleDeleteProfile(item.key)}
                      >
                        删除
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <div className="memory-form-row">
                <input
                  className="field input"
                  style={{ maxWidth: 180 }}
                  placeholder="键，如 学习目标"
                  value={newKey}
                  onChange={(e) => setNewKey(e.target.value)}
                  aria-label="新画像键"
                />
                <input
                  className="field input"
                  placeholder="值"
                  value={newValue}
                  onChange={(e) => setNewValue(e.target.value)}
                  aria-label="新画像值"
                />
                <button type="button" className="btn btn-sm btn-ghost" onClick={() => void handleAddProfile()}>
                  添加
                </button>
              </div>

              <div className="memory-subhead">情节记忆（最近 {mem.episodic.shown} 条）</div>
              {mem.episodic.shown === 0 ? (
                <p className="muted" style={{ fontSize: 12 }}>暂无情节记录。</p>
              ) : (
                <ul className="memory-entry-list">
                  {mem.episodic.recent.map((e) => (
                    <li key={e.id} className="memory-entry">
                      <time>{fmtTs(e.ts)}</time>
                      <span className="memory-kind">{e.kind}</span>
                      <span className="memory-entry-summary">{e.summary}</span>
                    </li>
                  ))}
                </ul>
              )}

              <div className="memory-subhead">语义记忆（最近 {mem.semantic.shown} 条）</div>
              {mem.semantic.shown === 0 ? (
                <p className="muted" style={{ fontSize: 12 }}>暂无沉淀的事实。</p>
              ) : (
                <ul className="memory-entry-list">
                  {mem.semantic.recent.map((f) => (
                    <li key={f.id} className="memory-entry">
                      <time>{fmtTs(f.ts)}</time>
                      <span className="memory-entry-summary">
                        {f.subject} · {f.relation} · {f.object}
                      </span>
                    </li>
                  ))}
                </ul>
              )}

              <div className="memory-subhead">工作记忆</div>
              <div className="memory-form-row">
                <span className="muted" style={{ fontSize: 12 }}>
                  当前 {mem.working.size} 条 · 进程内，重启即空
                </span>
                <button
                  type="button"
                  className="btn btn-sm btn-ghost"
                  onClick={() => void handleClearWorking()}
                  disabled={busyZone === 'working'}
                >
                  清空
                </button>
              </div>

              <div className="memory-subhead">情节保留天数</div>
              <div className="memory-form-row">
                <input
                  className="field input"
                  type="number"
                  min={0}
                  max={RETENTION_MAX}
                  style={{ maxWidth: 120 }}
                  value={retention}
                  onChange={(e) => setRetention(e.target.value)}
                  onBlur={saveRetention}
                  aria-label="情节记忆保留天数"
                />
                <button type="button" className="btn btn-sm btn-ghost" onClick={saveRetention}>
                  保存
                </button>
              </div>
              <p className="muted" style={{ fontSize: 12 }}>
                0 = 不按天自动清（交给 Agent 管理）；大于 0 = 打开本页时清理超过天数的情节。
              </p>

              <div className="memory-subhead">清空记忆</div>
              <div className="memory-zone-grid">
                {(['profile', 'episodic', 'semantic'] as const).map((z) => (
                  <button
                    key={z}
                    type="button"
                    className="btn btn-sm btn-danger"
                    onClick={() => setConfirmZone(z)}
                  >
                    清空{ZONE_LABELS[z]}
                  </button>
                ))}
                <button
                  type="button"
                  className="btn btn-sm btn-danger"
                  onClick={() => setConfirmZone('all')}
                  data-testid="clear-memory-all-btn"
                >
                  清空全部
                </button>
              </div>
            </>
          )}
        </div>
      </section>

      {confirmZone && confirmZone !== 'working' && (
        <ConfirmDialog
          open
          title={`清空${ZONE_LABELS[confirmZone]}`}
          message={CONFIRM_MESSAGES[confirmZone]}
          confirmLabel="清空"
          danger
          onConfirm={() => void handleClearMemory()}
          onCancel={() => setConfirmZone(null)}
        />
      )}
    </>
  );
}
