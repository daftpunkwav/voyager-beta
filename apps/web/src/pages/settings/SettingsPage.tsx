import { Link } from 'react-router-dom';
import { useState } from 'react';
import { useSettings } from '@/hooks/useSettings';
import { useTheme } from '@/hooks/useTheme';
import { useGithubAccounts } from '@/hooks/useProjects';
import { getApi } from '@/api/client';
import { useUIStore } from '@/stores/uiStore';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { LlmSettingsSection } from '@/components/settings/LlmSettingsSection';
import { AgentSettingsSection } from '@/components/settings/AgentSettingsSection';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { useSettingsStore } from '@/stores/settingsStore';

type Section = 'appearance' | 'github' | 'llm' | 'agent' | 'data' | 'about';

const NAV: { id: Section; label: string; icon: string }[] = [
  { id: 'appearance', label: '外观', icon: '◐' },
  { id: 'github', label: 'GitHub', icon: '⌂' },
  { id: 'llm', label: 'LLM', icon: '◇' },
  { id: 'agent', label: 'Agent', icon: '◎' },
  { id: 'data', label: '数据', icon: '▤' },
  { id: 'about', label: '关于', icon: 'i' },
];

export function SettingsPage() {
  const { settings, isLoading, updateSettings, saveLlmApiKey, testLLM, isTestingLLM, testResult } =
    useSettings();
  const error = useSettingsStore((s) => s.error);
  const loadSettings = useSettingsStore((s) => s.loadSettings);
  const { theme, setTheme, fontScale, setFontScale } = useTheme();
  const { data: accounts = [], refetch: refetchAccounts } = useGithubAccounts();
  const addToast = useUIStore((s) => s.addToast);
  const [section, setSection] = useState<Section>('appearance');
  const [ghUser, setGhUser] = useState('');
  const [ghPat, setGhPat] = useState('');
  const [unbindId, setUnbindId] = useState<string | null>(null);

  // 修复 v2:之前是 `if (isLoading || !settings)` — 当后端 500 时
  // isLoading=false 但 settings 仍为 null,导致页面永远停在 LoadingSpinner
  // 卡死(用户无法看到内容/降级 UI)。
  if (isLoading && !settings) {
    return (
      <div className="page-scaffold">
        <LoadingSpinner label="加载设置中…" />
      </div>
    );
  }
  if (!settings) {
    // 后端不可达,显示降级 + 重试入口(避免白屏)
    return (
      <div className="page-scaffold">
        <div className="page-scaffold__state">
          <EmptyState
            title="无法加载设置"
            description={error ?? '后端服务未启动或不可达。请检查 gateway 是否运行后重试。'}
            icon={EmptyStateIcons.settings}
            action={
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => void loadSettings()}
              >
                重试
              </button>
            }
          />
        </div>
      </div>
    );
  }

  const bindGithub = async () => {
    try {
      await getApi().bindGithub({ username: ghUser, pat: ghPat });
      setGhPat('');
      void refetchAccounts();
      addToast({ type: 'success', message: 'GitHub 绑定成功' });
    } catch {
      addToast({ type: 'error', message: '绑定失败' });
    }
  };

  const unbindGithub = async (id: string) => {
    await getApi().unbindGithub(id);
    void refetchAccounts();
    addToast({ type: 'success', message: '已解绑' });
  };

  const exportProjects = async () => {
    const res = await getApi().exportProjects();
    const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'projects-export.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportNotes = async () => {
    const res = await getApi().listAllNotes();
    const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'notes-export.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="page-scaffold settings-page">
      <header className="page-scaffold__head">
        <div>
          <h1>设置</h1>
          <p className="page-scaffold__subtitle">个性化、账号、模型与数据管理</p>
        </div>
      </header>
      <div className="settings-shell">
        <nav className="subnav" aria-label="设置分类">
          <div className="subnav-title">分类</div>
        {NAV.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`subnav-item ${section === item.id ? 'active' : ''}`}
            onClick={() => setSection(item.id)}
          >
            <span className="subnav-icon" aria-hidden>
              {item.icon}
            </span>
            {item.label}
            {item.id === 'llm' && !settings.llm_configured && <span className="dot-unset" />}
          </button>
        ))}
      </nav>

      <div className="settings-main">
        {section === 'appearance' && (
          <section className="settings-section glass-card glass-card--overview-outer">
            <h2>外观</h2>
            <p className="section-desc">主题与阅读舒适度</p>
            <div className="theme-cards">
              {(['light', 'dark', 'system'] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  className={`theme-card ${theme === t ? 'active' : ''}`}
                  onClick={() => {
                    setTheme(t);
                    if (t !== 'system') void updateSettings({ theme: t });
                  }}
                >
                  <div className={`theme-preview pv-${t === 'system' ? 'auto' : t}`}>
                    <div className="pv-side">
                      <i className="on" />
                      <i />
                      <i />
                    </div>
                    <div className="pv-body">
                      <i className="t" />
                      <i />
                    </div>
                  </div>
                  <div className="theme-card-label">
                    {t === 'light' ? '浅色' : t === 'dark' ? '深色' : '跟随系统'}
                    <span className="theme-card-check">✓</span>
                  </div>
                </button>
              ))}
            </div>
            <div className="font-row" style={{ marginTop: 24 }}>
              <div className="font-slider-block form-row">
                <label className="field-label">
                  字体缩放 <span className="val">{fontScale.toFixed(1)}×</span>
                </label>
                <input
                  type="range"
                  className="slider"
                  min={0.8}
                  max={1.5}
                  step={0.1}
                  value={fontScale}
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    setFontScale(v);
                    void updateSettings({ font_scale: v });
                  }}
                />
              </div>
              <div className="font-preview">
                <div className="fp-sample">
                  <span className="fp-aa">Aa</span>
                  <span className="fp-cn">阅读预览</span>
                </div>
                <div className="fp-en">The quick brown fox</div>
              </div>
            </div>
          </section>
        )}

        {section === 'github' && (
          <section className="settings-section glass-card glass-card--overview-outer">
            <h2>GitHub</h2>
            <p className="section-desc">绑定账号以同步 Stars</p>
            {accounts.map((a) => (
              <div key={a.id} className="gh-card" style={{ marginBottom: 16 }}>
                <div className="gh-avatar">{a.username[0]?.toUpperCase()}</div>
                <div className="gh-meta">
                  <div className="gh-handle">@{a.username}</div>
                  <div className="gh-sub">已绑定 · {new Date(a.bound_at).toLocaleDateString('zh-CN')}</div>
                </div>
                <div className="gh-actions">
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => setUnbindId(a.id)}>
                    解绑
                  </button>
                </div>
              </div>
            ))}
            <div className="form-row">
              <label>GitHub 用户名</label>
              <input className="field input" value={ghUser} onChange={(e) => setGhUser(e.target.value)} />
            </div>
            <div className="form-row">
              <label>Personal Access Token</label>
              <input
                className="field input"
                type="password"
                value={ghPat}
                onChange={(e) => setGhPat(e.target.value)}
              />
            </div>
            <button type="button" className="btn btn-primary" onClick={() => void bindGithub()}>
              绑定账号
            </button>
          </section>
        )}

        {section === 'llm' && (
          <section className="settings-section glass-card glass-card--overview-outer">
            <h2>LLM 配置</h2>
            <p className="section-desc">供应商连接、模型列表与各 Agent 的模型与说话风格</p>
            <LlmSettingsSection
              settings={settings}
              updateSettings={updateSettings}
              testLLM={testLLM}
              isTestingLLM={isTestingLLM}
              testResult={testResult}
              onSaveApiKey={async (key, providerId) => {
                try {
                  await saveLlmApiKey(key, providerId);
                  addToast({ type: 'success', message: 'API Key 已保存' });
                } catch {
                  addToast({ type: 'error', message: 'API Key 保存失败' });
                }
              }}
            />
            <p style={{ marginTop: 12, fontSize: 13 }}>
              <Link to="/usage" style={{ color: 'var(--brand-500)' }}>
                查看 LLM 用量 →
              </Link>
            </p>
          </section>
        )}

        {section === 'agent' && (
          <AgentSettingsSection settings={settings} updateSettings={updateSettings} />
        )}

        {section === 'data' && (
          <section className="settings-section glass-card glass-card--overview-outer">
            <h2>数据</h2>
            <p className="section-desc">导出本地项目与笔记</p>
            <button type="button" className="btn btn-primary" style={{ marginRight: 8 }} onClick={() => void exportProjects()}>
              导出项目 JSON
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => void exportNotes()}>
              导出笔记 JSON
            </button>
          </section>
        )}

        {section === 'about' && (
          <section className="settings-section glass-card glass-card--overview-outer">
            <h2>关于 Voyager</h2>
            <div className="about-row">
              <span className="k">版本</span>
              <span>v1.0.0</span>
            </div>
            <div className="about-row">
              <span className="k">定位</span>
              <span>GitHub 项目学习驾驶舱</span>
            </div>
          </section>
        )}
      </div>
    </div>

    <ConfirmDialog
      open={unbindId !== null}
      title="解绑 GitHub"
      message="确定解绑此账号？"
      danger
      onConfirm={() => {
        if (unbindId) void unbindGithub(unbindId);
        setUnbindId(null);
      }}
      onCancel={() => setUnbindId(null)}
    />
  </div>
);
}
