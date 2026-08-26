// @ts-nocheck — 迁移期:RepoPilot 风格代码,新 page / hook 仍按 strict 写(见各文件顶部注释)。
import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getApi } from '@/api/client';
import type { Goal, MemoryItem, Project, UserProfile } from '@/api/types';
import { useAgentStore } from '@/stores/agentStore';
import { formatNumber, REPO_AVATAR_GRADIENTS, splitRepoName } from '@/utils/format';
import { formatMemoryChipContent } from '@/utils/agentQuestion';
import { ProgressBadge } from '@/components/project/ProgressBadge';
import { ContextWindowPanel } from './ContextWindowPanel';

const MEMORY_LABELS: Record<MemoryItem['category'], string> = {
  summary: '记忆摘要',
  goal: '学习目标',
  tech: '技术栈',
  preference: '偏好',
};

/** 各记忆区块的维护策略 */
const MEMORY_SECTION_META: Record<
  MemoryItem['category'],
  { userCanAdd: boolean; userCanRemove: boolean; hint: string }
> = {
  summary: {
    userCanAdd: false,
    userCanRemove: false,
    hint: '由 Agent 根据对话自动维护',
  },
  goal: {
    userCanAdd: false,
    userCanRemove: true,
    hint: '可手动添加目标，掌握进度由 Agent 更新',
  },
  tech: {
    userCanAdd: false,
    userCanRemove: false,
    hint: '由 Agent 根据学习轨迹自动归纳',
  },
  preference: {
    userCanAdd: true,
    userCanRemove: true,
    hint: '你与 Agent 均可维护偏好词条',
  },
};

const MAX_MEMORY_LENGTH = 500;
const MAX_GOAL_LENGTH = 200;

interface AgentContextSidebarProps {
  sessionId?: string | null;
  toolLogOpen: boolean;
  onToggleToolLog: () => void;
  toolCalls: Map<string, { name: string; result?: unknown }>;
}

export function AgentContextSidebar({
  sessionId,
  toolLogOpen,
  onToggleToolLog,
  toolCalls,
}: AgentContextSidebarProps) {
  const qc = useQueryClient();
  const [projectSearch, setProjectSearch] = useState('');
  const [pickerOpen, setPickerOpen] = useState(false);
  const contextRevision = useAgentStore((s) => s.contextRevision);

  const { data: profile } = useQuery({
    queryKey: ['userProfile'],
    queryFn: async () => (await getApi().getUserProfile()).data,
  });

  // 写操作成功后刷新会话绑定项目与项目库
  useEffect(() => {
    if (contextRevision <= 0) return;
    void qc.invalidateQueries({ queryKey: ['agentSession', sessionId] });
    void qc.invalidateQueries({ queryKey: ['sessionBoundProjects'] });
    void qc.invalidateQueries({ queryKey: ['projects'] });
    void qc.invalidateQueries({ queryKey: ['userProfile'] });
    void qc.invalidateQueries({ queryKey: ['notes'] });
  }, [contextRevision, qc, sessionId]);

  // 随活跃会话拉取真实绑定项目
  const { data: sessionDetail } = useQuery({
    queryKey: ['agentSession', sessionId],
    enabled: Boolean(sessionId),
    queryFn: async () => {
      if (!sessionId) return null;
      return (await getApi().getAgentSession(sessionId)).data;
    },
  });

  const boundIds = useMemo(() => {
    if (!sessionDetail) return [] as string[];
    if (sessionDetail.project_ids?.length) return sessionDetail.project_ids.map(String);
    if (sessionDetail.project_id) return [String(sessionDetail.project_id)];
    return [];
  }, [sessionDetail]);

  // 拉取绑定项目详情（并行 getProject；数量通常很少）
  const { data: boundProjects = [] } = useQuery({
    queryKey: ['sessionBoundProjects', sessionId, boundIds.join(',')],
    enabled: boundIds.length > 0,
    queryFn: async () => {
      const api = getApi();
      const results = await Promise.all(
        boundIds.map(async (id) => {
          try {
            return (await api.getProject(id)).data;
          } catch {
            return null;
          }
        })
      );
      return results.filter((p): p is Project => Boolean(p));
    },
  });

  // 添加项目：轻量搜索库
  const { data: searchResults } = useQuery({
    queryKey: ['projectPicker', projectSearch],
    enabled: pickerOpen,
    queryFn: async () => {
      const res = await getApi().listProjects({
        search: projectSearch.trim() || undefined,
        page: 1,
        page_size: 12,
      });
      return res.data.items;
    },
  });

  // 工具 manage_session_projects / propose_memory 完成后刷新
  useEffect(() => {
    for (const tc of toolCalls.values()) {
      const r = tc.result as Record<string, unknown> | undefined;
      if (r && r.__session_projects__ && sessionId) {
        void qc.invalidateQueries({ queryKey: ['agentSession', sessionId] });
        void qc.invalidateQueries({ queryKey: ['sessionBoundProjects'] });
        void qc.invalidateQueries({ queryKey: ['userProfile'] });
      }
      if (tc.name === 'propose_memory' && tc.result !== undefined) {
        void qc.invalidateQueries({ queryKey: ['userProfile'] });
      }
    }
  }, [toolCalls, sessionId, qc]);

  // 会话列表中的 project_ids 变化时（SSE session_projects）同步刷新详情
  const storeProjectIds = useAgentStore((s) => {
    const cur = s.sessions.find((x) => x.id === sessionId);
    return (cur?.project_ids ?? []).join(',');
  });
  useEffect(() => {
    if (!sessionId) return;
    void qc.invalidateQueries({ queryKey: ['agentSession', sessionId] });
    void qc.invalidateQueries({ queryKey: ['sessionBoundProjects'] });
  }, [storeProjectIds, sessionId, qc]);

  const updateProfile = useMutation({
    mutationFn: async (data: Partial<UserProfile>) =>
      (await getApi().updateUserProfile(data)).data,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['userProfile'] }),
  });

  const resolveProposal = useMutation({
    mutationFn: async (args: { id: string; action: 'accept' | 'reject' }) => {
      const api = getApi();
      if (args.action === 'accept') {
        return (await api.acceptMemoryProposal(args.id)).data;
      }
      return (await api.rejectMemoryProposal(args.id)).data;
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['userProfile'] }),
  });

  const [editingCategory, setEditingCategory] = useState<MemoryItem['category'] | 'goal' | null>(
    null
  );
  const [editValue, setEditValue] = useState('');
  const [editError, setEditError] = useState<string | null>(null);

  const memoryItems = profile?.memory_items ?? [];
  const pendingProposals = profile?.pending_memory_proposals ?? [];
  const goals = profile?.goals ?? [];

  // 技术栈：优先 memory_items tech；若空则从 tech_proficiency 派生
  // 兜底空数组每次渲染生成新引用，故在 useMemo 内部兜底避免依赖失稳
  const techChips = useMemo(() => {
    const items = profile?.memory_items ?? [];
    const fromMem = items.filter((m) => m.category === 'tech');
    if (fromMem.length > 0) return fromMem.map((m) => m.content);
    const tech = profile?.tech_proficiency ?? {};
    return Object.entries(tech).map(([k, v]) => `${k}: ${v}`);
  }, [profile?.memory_items, profile?.tech_proficiency]);

  const startEditing = (category: MemoryItem['category'] | 'goal') => {
    setEditingCategory(category);
    setEditValue('');
    setEditError(null);
  };

  const cancelEditing = () => {
    setEditingCategory(null);
    setEditValue('');
    setEditError(null);
  };

  const validateAndAddMemory = (category: MemoryItem['category']) => {
    const content = editValue.trim();
    if (!content) {
      setEditError('内容不能为空');
      return;
    }
    if (content.length > MAX_MEMORY_LENGTH) {
      setEditError(`内容不能超过 ${MAX_MEMORY_LENGTH} 个字符`);
      return;
    }
    const item: MemoryItem = {
      id: `mem_${Date.now()}`,
      category,
      content,
      created_at: new Date().toISOString(),
    };
    void updateProfile.mutate({ memory_items: [...memoryItems, item] });
    cancelEditing();
  };

  const validateAndAddGoal = () => {
    const title = editValue.trim();
    if (!title) {
      setEditError('目标不能为空');
      return;
    }
    if (title.length > MAX_GOAL_LENGTH) {
      setEditError(`目标不能超过 ${MAX_GOAL_LENGTH} 个字符`);
      return;
    }
    const goal: Goal = {
      title,
      priority: goals.length + 1,
      status: 'active',
    };
    void updateProfile.mutate({ goals: [...goals, goal] });
    cancelEditing();
  };

  const removeMemory = (id: string) => {
    void updateProfile.mutate({
      memory_items: memoryItems.filter((m) => m.id !== id),
    });
  };

  const removeGoal = (index: number) => {
    void updateProfile.mutate({
      goals: goals.filter((_, i) => i !== index),
    });
  };

  const itemsByCategory = (cat: MemoryItem['category']) =>
    memoryItems.filter((m) => m.category === cat);

  const setBoundProjects = async (ids: string[]) => {
    if (!sessionId) return;
    await getApi().updateAgentSession(sessionId, { project_ids: ids });
    void qc.invalidateQueries({ queryKey: ['agentSession', sessionId] });
  };

  const addProject = (id: string) => {
    if (boundIds.includes(id)) return;
    void setBoundProjects([...boundIds, id]);
    setPickerOpen(false);
    setProjectSearch('');
  };

  const removeProject = (id: string) => {
    void setBoundProjects(boundIds.filter((x) => x !== id));
  };

  return (
    <aside className="context-panel">
      <div className="context-section context-section--projects">
        <div className="context-title">
          <span>
            当前上下文
            {boundProjects.length > 0 ? ` · ${boundProjects.length}` : ''}
          </span>
          {sessionId && (
            <button
              type="button"
              className="ctx-add-btn"
              title="添加项目"
              onClick={() => setPickerOpen((v) => !v)}
            >
              +
            </button>
          )}
        </div>

        {!sessionId && (
          <p className="ctx-proj-hint muted">选择或新建对话后可绑定项目</p>
        )}

        {sessionId && boundProjects.length === 0 && !pickerOpen && (
          <p className="ctx-proj-empty muted">
            尚未绑定项目。与 Hub 对话提到仓库时会自动加入，或点 + 手动添加。
          </p>
        )}

        <div className="ctx-proj-chips">
          {boundProjects.map((p, i) => {
            const { repo } = splitRepoName(p.name);
            return (
              <div key={p.id} className="ctx-proj-chip" title={p.name}>
                <span
                  className="ctx-proj-chip__icon"
                  style={{ background: REPO_AVATAR_GRADIENTS[i % REPO_AVATAR_GRADIENTS.length] }}
                >
                  {(repo[0] ?? 'P').toUpperCase()}
                </span>
                <span className="ctx-proj-chip__name">{p.name}</span>
                <ProgressBadge progress={p.progress} />
                <button
                  type="button"
                  className="ctx-proj-chip__remove"
                  aria-label={`移除 ${p.name}`}
                  onClick={() => removeProject(p.id)}
                >
                  ×
                </button>
              </div>
            );
          })}
        </div>

        {pickerOpen && sessionId && (
          <div className="ctx-proj-picker">
            <input
              className="input input--compact"
              placeholder="搜索项目库…"
              value={projectSearch}
              onChange={(e) => setProjectSearch(e.target.value)}
              autoFocus
            />
            <div className="ctx-proj-picker__list">
              {(searchResults ?? [])
                .filter((p) => !boundIds.includes(p.id))
                .map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    className="ctx-proj-picker__item"
                    onClick={() => addProject(p.id)}
                  >
                    <span>{p.name}</span>
                    <span className="muted">
                      {p.language ?? '-'} · ★{formatNumber(p.stars)}
                    </span>
                  </button>
                ))}
              {(searchResults ?? []).filter((p) => !boundIds.includes(p.id)).length === 0 && (
                <p className="muted" style={{ fontSize: 11, padding: 6 }}>
                  无匹配项目
                </p>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="context-panel-scroll">
        {pendingProposals.length > 0 && (
          <div className="context-section context-section--memory">
            <div className="context-title">
              <span>待确认记忆</span>
            </div>
            <div className="context-memory-scroll">
              {pendingProposals.map((p) => (
                <div key={p.id} className="memory-chip memory-chip--pending" title={p.value}>
                  <span>
                    [{p.agent_id}/{p.kind}] {p.value.slice(0, 80)}
                    {p.value.length > 80 ? '…' : ''}
                  </span>
                  <div className="ctx-edit-actions">
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      disabled={resolveProposal.isPending}
                      onClick={() =>
                        resolveProposal.mutate({ id: p.id, action: 'accept' })
                      }
                    >
                      确认
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      disabled={resolveProposal.isPending}
                      onClick={() =>
                        resolveProposal.mutate({ id: p.id, action: 'reject' })
                      }
                    >
                      拒绝
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        {(['summary', 'goal', 'tech', 'preference'] as const).map((cat) => {
          const meta = MEMORY_SECTION_META[cat];
          const isEditing = editingCategory === cat;
          const isEmpty =
            cat === 'goal'
              ? goals.length === 0
              : cat === 'tech'
                ? techChips.length === 0
                : itemsByCategory(cat).length === 0;

          return (
            <div key={cat} className="context-section context-section--memory">
              <div className="context-title">
                <span>{MEMORY_LABELS[cat]}</span>
                {meta.userCanAdd && !isEditing && (
                  <button
                    type="button"
                    className="ctx-add-btn"
                    title={`添加${MEMORY_LABELS[cat]}`}
                    onClick={() => startEditing(cat)}
                  >
                    +
                  </button>
                )}
              </div>
              <div className="context-memory-scroll">
                {cat === 'goal'
                  ? goals.map((g, i) => (
                      <div key={`${g.title}-${i}`} className="memory-chip">
                        <span>{g.title}</span>
                        {meta.userCanRemove && (
                          <button type="button" aria-label="删除" onClick={() => removeGoal(i)}>
                            ×
                          </button>
                        )}
                      </div>
                    ))
                  : cat === 'tech'
                    ? techChips.map((content) => (
                        <div key={content} className="memory-chip">
                          <span>{content}</span>
                        </div>
                      ))
                    : itemsByCategory(cat).map((m) => (
                        <div key={m.id} className="memory-chip" title={m.content}>
                          <span>{formatMemoryChipContent(m.content)}</span>
                          {meta.userCanRemove && (
                            <button
                              type="button"
                              aria-label="删除"
                              onClick={() => removeMemory(m.id)}
                            >
                              ×
                            </button>
                          )}
                        </div>
                      ))}
                {isEditing && (
                  <div className="memory-chip memory-chip--editing">
                    <input
                      className="input input--compact"
                      value={editValue}
                      onChange={(e) => {
                        setEditValue(e.target.value);
                        setEditError(null);
                      }}
                      placeholder={cat === 'goal' ? '输入新目标…' : `输入${MEMORY_LABELS[cat]}…`}
                      maxLength={cat === 'goal' ? MAX_GOAL_LENGTH : MAX_MEMORY_LENGTH}
                      autoFocus
                    />
                    {editError && <span className="ctx-edit-error">{editError}</span>}
                    <div className="ctx-edit-actions">
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        onClick={() =>
                          cat === 'goal' ? validateAndAddGoal() : validateAndAddMemory(cat)
                        }
                      >
                        保存
                      </button>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={cancelEditing}>
                        取消
                      </button>
                    </div>
                  </div>
                )}
                {isEmpty && !isEditing && (
                  <p className="context-memory-empty muted">{meta.hint}</p>
                )}
              </div>
              {cat === 'goal' && !isEditing && (
                <button
                  type="button"
                  className="btn btn-ghost btn-sm ctx-add-goal-btn"
                  onClick={() => startEditing('goal')}
                >
                  添加目标
                </button>
              )}
            </div>
          );
        })}

        <div className="context-section">
          <button
            type="button"
            className="context-title collapsible-head"
            style={{
              width: '100%',
              border: 0,
              background: 'transparent',
              cursor: 'pointer',
              padding: 0,
            }}
            onClick={onToggleToolLog}
          >
            <span>工具调用日志</span>
            <svg
              className={`chev-down ${toolLogOpen ? 'open' : ''}`}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              width={12}
              height={12}
            >
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>
          {toolLogOpen && (
            <div className="context-memory-scroll context-memory-scroll--tool-log">
              <div className="tool-log">
                {toolCalls.size === 0 ? (
                  <div style={{ fontSize: 11, color: 'var(--text-400)' }}>暂无工具调用</div>
                ) : (
                  Array.from(toolCalls.entries()).map(([id, tc]) => (
                    <div
                      key={id}
                      className={`tool-log-row ${tc.result !== undefined ? 'success' : 'running'}`}
                    >
                      {tc.result !== undefined ? <span className="check">✓</span> : <span className="dot" />}
                      <span>{tc.name}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="context-section context-section--footer">
        <ContextWindowPanel sessionId={sessionId} compact />
      </div>
    </aside>
  );
}
