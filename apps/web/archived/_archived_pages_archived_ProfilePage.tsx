import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getApi } from '@/api/client';
import type { LearnerIdentity, UserProfile } from '@/api/types';
import { GlassCard } from '@/components/common/GlassCard';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { useAuthStore } from '@/stores/authStore';
import { useUIStore } from '@/stores/uiStore';

const EMPTY_IDENTITY: LearnerIdentity = {
  preferred_name: '',
  spoken_languages: [],
  programming_languages: [],
  tech_stack: [],
  interests: [],
  occupation: '',
  experience_level: '',
  bio: '',
};

const EXPERIENCE_OPTIONS: Array<{ value: LearnerIdentity['experience_level']; label: string }> = [
  { value: '', label: '未设置' },
  { value: 'beginner', label: '入门' },
  { value: 'intermediate', label: '中级' },
  { value: 'advanced', label: '进阶' },
];

function listToText(items: string[] | undefined): string {
  return (items ?? []).join(', ');
}

function textToList(text: string): string[] {
  return text
    .split(/[,，、\n]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 32);
}

export function ProfilePage() {
  const fetchMe = useAuthStore((s) => s.fetchMe);
  const addToast = useUIStore((s) => s.addToast);
  const [draft, setDraft] = useState<LearnerIdentity>(EMPTY_IDENTITY);
  const [saving, setSaving] = useState(false);

  const { data: learningProfile, isLoading, refetch: refetchProfile } = useQuery({
    queryKey: ['userProfile'],
    queryFn: async () => (await getApi().getUserProfile()).data,
  });

  useEffect(() => {
    if (!learningProfile?.identity) return;
    setDraft({ ...EMPTY_IDENTITY, ...learningProfile.identity });
  }, [learningProfile]);

  if (isLoading && !learningProfile) return <LoadingSpinner />;

  const displayName = draft.preferred_name.trim() || '学习者';
  const initial = displayName.charAt(0).toUpperCase();

  const saveIdentity = async () => {
    setSaving(true);
    try {
      await getApi().updateUserProfile({
        identity: {
          preferred_name: draft.preferred_name.trim(),
          spoken_languages: draft.spoken_languages,
          programming_languages: draft.programming_languages,
          tech_stack: draft.tech_stack,
          interests: draft.interests,
          occupation: draft.occupation.trim(),
          experience_level: draft.experience_level || '',
          bio: draft.bio.trim(),
        },
      });
      await refetchProfile();
      await fetchMe();
      addToast({ type: 'success', message: '个人信息已保存' });
    } catch {
      addToast({ type: 'error', message: '保存失败' });
    } finally {
      setSaving(false);
    }
  };

  const setListField = (
    key: 'spoken_languages' | 'programming_languages' | 'tech_stack' | 'interests',
    text: string
  ) => {
    setDraft((prev) => ({ ...prev, [key]: textToList(text) }));
  };

  return (
    <div className="page profile-page">
      <GlassCard className="profile-header glass-card--overview-outer">
        <span className="profile-header__avatar profile-header__avatar--placeholder" aria-hidden>
          {initial}
        </span>
        <h1>{displayName}</h1>
        <p className="profile-header__hint">本机学习者信息 · Agent 按需读取</p>
      </GlassCard>

      <GlassCard className="glass-card--overview-outer">
        <h2>个人信息补充</h2>
        <p className="muted small profile-lead">
          填写后 Agent 不会自动加载全部内容；仅在对话需要时按字段拉取（如称呼、技术栈）。
        </p>

        <label className="form-field">
          称呼（Agent 怎么叫你）
          <input
            className="input"
            value={draft.preferred_name}
            onChange={(e) => setDraft((p) => ({ ...p, preferred_name: e.target.value }))}
            placeholder="例如：小明 / Alex"
            maxLength={64}
          />
        </label>

        <label className="form-field">
          身份 / 职业
          <input
            className="input"
            value={draft.occupation}
            onChange={(e) => setDraft((p) => ({ ...p, occupation: e.target.value }))}
            placeholder="例如：在校学生、前端工程师"
            maxLength={64}
          />
        </label>

        <label className="form-field">
          经验水平
          <select
            className="input"
            value={draft.experience_level || ''}
            onChange={(e) =>
              setDraft((p) => ({
                ...p,
                experience_level: e.target.value as LearnerIdentity['experience_level'],
              }))
            }
          >
            {EXPERIENCE_OPTIONS.map((opt) => (
              <option key={opt.value || 'unset'} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>

        <label className="form-field">
          熟练自然语言
          <input
            className="input"
            value={listToText(draft.spoken_languages)}
            onChange={(e) => setListField('spoken_languages', e.target.value)}
            placeholder="用逗号分隔，例如：中文, English"
          />
        </label>

        <label className="form-field">
          熟练编程语言
          <input
            className="input"
            value={listToText(draft.programming_languages)}
            onChange={(e) => setListField('programming_languages', e.target.value)}
            placeholder="例如：TypeScript, Python, Go"
          />
        </label>

        <label className="form-field">
          技术栈 / 工具
          <input
            className="input"
            value={listToText(draft.tech_stack)}
            onChange={(e) => setListField('tech_stack', e.target.value)}
            placeholder="例如：React, FastAPI, PostgreSQL"
          />
        </label>

        <label className="form-field">
          兴趣方向
          <input
            className="input"
            value={listToText(draft.interests)}
            onChange={(e) => setListField('interests', e.target.value)}
            placeholder="例如：系统设计, 开源学习路径, Agent"
          />
        </label>

        <label className="form-field">
          一句话简介
          <textarea
            className="input profile-textarea"
            rows={3}
            value={draft.bio}
            onChange={(e) => setDraft((p) => ({ ...p, bio: e.target.value }))}
            placeholder="简单介绍学习背景或当前目标…"
            maxLength={500}
          />
        </label>

        <button
          type="button"
          className="btn btn-primary"
          disabled={saving}
          onClick={() => void saveIdentity()}
        >
          {saving ? '保存中…' : '保存个人信息'}
        </button>
      </GlassCard>

      <GlassCard className="glass-card--overview-outer">
        <h2>Agent 共享记忆（只读预览）</h2>
        <p className="muted small">
          由 Hub 统筹维护：对话中推断的熟练度、目标与长期记忆。清除记忆不会删除上方自填信息。
        </p>
        {learningProfile ? <AgentMemoryPreview profile={learningProfile} /> : (
          <p className="muted">加载中…</p>
        )}
      </GlassCard>
    </div>
  );
}

function AgentMemoryPreview({ profile }: { profile: UserProfile }) {
  const tech = profile.tech_proficiency ?? {};
  const prefs = profile.learning_preferences ?? {};
  const goals = profile.goals ?? [];
  const memory = profile.memory_items ?? [];

  return (
    <dl className="profile-dl">
      <dt>历史摘要</dt>
      <dd>{profile.history_summary || '暂无'}</dd>
      <dt>技术熟练度</dt>
      <dd>
        {Object.keys(tech).length === 0
          ? '暂无'
          : Object.entries(tech)
              .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
              .join(' · ')}
      </dd>
      <dt>学习偏好</dt>
      <dd>{Object.keys(prefs).length === 0 ? '暂无' : JSON.stringify(prefs)}</dd>
      <dt>目标</dt>
      <dd>{goals.length === 0 ? '暂无' : goals.map((g) => g.title).join('；')}</dd>
      <dt>长期记忆</dt>
      <dd>
        {memory.length === 0
          ? '暂无'
          : memory
              .slice(0, 8)
              .map((m) => m.content)
              .join(' · ')}
      </dd>
    </dl>
  );
}
