import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAgentStore } from '@/stores/agentStore';
import { ChatPanel } from '@/components/agent/ChatPanel';
import { AgentContextSidebar } from '@/components/agent/AgentContextSidebar';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { formatRelativeTime } from '@/utils/date';
import { AGENT_TAG_CLASS } from '@/utils/labels';
import { personaDisplayName } from '@/constants/personas';
import type { AgentSession } from '@/api/types';
import { STORAGE, migrateKey, readKey, writeKey } from '@/brand';

migrateKey(STORAGE.sessionDrawer, STORAGE.legacy.sessionDrawer);
migrateKey(STORAGE.contextDrawer, STORAGE.legacy.contextDrawer);

/** 详情页快速分析会话（折叠显示） */
function isAnalyzeSession(s: AgentSession): boolean {
  if (s.source === 'analyze') return true;
  const t = (s.title || '').trim();
  if (/^(scout|mentor|navigator|curator|scribe|atlas|recon|explainer|organizer|graph_guide)\s·\s/i.test(t)) return true;
  // 分析 owner/repo
  if (/^分析\s+\S+/.test(t)) return true;
  return false;
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      className={`chev-down ${open ? 'open' : ''}`}
      viewBox="0 0 24 24"
      width={12}
      height={12}
      aria-hidden
    >
      <path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

export function AgentPage() {
  const { sessionId } = useParams<{ sessionId?: string }>();
  const sessions = useAgentStore((s) => s.sessions);
  const currentSessionId = useAgentStore((s) => s.currentSessionId);
  const toolCalls = useAgentStore((s) => s.toolCalls);
  const loadSessions = useAgentStore((s) => s.loadSessions);
  const switchSession = useAgentStore((s) => s.switchSession);
  const createSession = useAgentStore((s) => s.createSession);
  const deleteSession = useAgentStore((s) => s.deleteSession);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [batchDeleteIds, setBatchDeleteIds] = useState<string[] | null>(null);
  const [sessionSearch, setSessionSearch] = useState('');
  const [toolLogOpen, setToolLogOpen] = useState(true);
  const [chatOpen, setChatOpen] = useState(true);
  const [analyzeOpen, setAnalyzeOpen] = useState(false);
  const [manageMode, setManageMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  // 会话列表 / 上下文面板改为浮层抽屉(overlay):打开时悬浮在对话区之上,不再挤占中间列。
  // 状态持久化到 localStorage;默认均关闭,保持对话区全宽。
  const [sessionListOpen, setSessionListOpen] = useState(() => {
    try {
      return readKey(STORAGE.sessionDrawer, STORAGE.legacy.sessionDrawer) === '1';
    } catch {
      return false;
    }
  });
  const [contextPanelOpen, setContextPanelOpen] = useState(() => {
    try {
      return readKey(STORAGE.contextDrawer, STORAGE.legacy.contextDrawer) === '1';
    } catch {
      return false;
    }
  });

  // 抽屉开关状态持久化到 localStorage;视觉类名直接绑定到 chat-layout 根节点,
  // 不再查询已废弃的 .agent-shell,避免 AppShell 重构后 DOM 操作失效。
  useEffect(() => {
    try {
      writeKey(STORAGE.sessionDrawer, sessionListOpen ? '1' : '0');
      writeKey(STORAGE.contextDrawer, contextPanelOpen ? '1' : '0');
    } catch {
      /* 隐私模式等场景下忽略 */
    }
  }, [sessionListOpen, contextPanelOpen]);

  // Esc 关闭任一打开的抽屉
  useEffect(() => {
    if (!sessionListOpen && !contextPanelOpen) return;
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSessionListOpen(false);
        setContextPanelOpen(false);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [sessionListOpen, contextPanelOpen]);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  const filteredSessions = useMemo(() => {
    const q = sessionSearch.toLowerCase();
    if (!q) return sessions;
    return sessions.filter((s) => s.title.toLowerCase().includes(q));
  }, [sessions, sessionSearch]);

  const chatSessions = useMemo(
    () => filteredSessions.filter((s) => !isAnalyzeSession(s)),
    [filteredSessions]
  );
  const analyzeSessions = useMemo(
    () => filteredSessions.filter((s) => isAnalyzeSession(s)),
    [filteredSessions]
  );

  const visibleForManage = useMemo(() => {
    const list: AgentSession[] = [];
    if (chatOpen) list.push(...chatSessions);
    if (analyzeOpen) list.push(...analyzeSessions);
    return list;
  }, [chatSessions, analyzeSessions, chatOpen, analyzeOpen]);

  useEffect(() => {
    if (sessionId) {
      // 已在目标会话时不要重复拉详情，避免 sessions 列表更新时冲掉内存中的 thinking
      if (currentSessionId !== sessionId) {
        void switchSession(sessionId);
      }
      return;
    }
    if (!currentSessionId && chatSessions.length > 0) {
      const first = chatSessions[0];
      if (first) void switchSession(first.id);
    }
  }, [sessionId, chatSessions, currentSessionId, switchSession]);

  // 切换会话时若目标落在折叠分组，展开该分组（仅随 sessionId 变化触发）
  const prevSessionIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (!currentSessionId || currentSessionId === prevSessionIdRef.current) return;
    prevSessionIdRef.current = currentSessionId;
    const target = sessions.find((s) => s.id === currentSessionId);
    if (!target) return;
    if (isAnalyzeSession(target)) setAnalyzeOpen(true);
    else setChatOpen(true);
  }, [currentSessionId, sessions]);

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAllVisible = () => {
    setSelectedIds(new Set(visibleForManage.map((s) => s.id)));
  };

  const clearSelection = () => setSelectedIds(new Set());

  const exitManage = () => {
    setManageMode(false);
    clearSelection();
  };

  const renderSessionItem = (s: AgentSession, kind: 'chat' | 'analyze') => (
    <div
      key={s.id}
      className={`session-item ${kind === 'analyze' ? 'session-item--analyze' : ''} ${
        currentSessionId === s.id ? 'active' : ''
      } ${selectedIds.has(s.id) ? 'session-item--selected' : ''}`}
      role="button"
      tabIndex={0}
      onClick={() => {
        if (manageMode) {
          toggleSelect(s.id);
          return;
        }
        void switchSession(s.id);
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          if (manageMode) toggleSelect(s.id);
          else void switchSession(s.id);
        }
      }}
    >
      {manageMode && (
        <label className="session-check" onClick={(e) => e.stopPropagation()}>
          <input
            type="checkbox"
            checked={selectedIds.has(s.id)}
            onChange={() => toggleSelect(s.id)}
            aria-label={`选择 ${s.title}`}
          />
        </label>
      )}
      <div className="session-item__main">
        <div className="session-title">
          {kind === 'analyze' && (
            <span className="session-source-chip" title="项目详情页快速调用">
              快析
            </span>
          )}
          <span className="session-title__text">{s.title}</span>
          {s.unread && <span className="session-unread" title="未读" />}
        </div>
        <div className="session-meta">
          <span className={`agent-tag ${AGENT_TAG_CLASS[s.agent] ?? 'agent-tag-orchestrator'}`}>
            {personaDisplayName(s.agent)}
          </span>
          <span>{formatRelativeTime(s.updated_at)}</span>
          {!manageMode && (
            <button
              type="button"
              className="icon-btn"
              style={{ marginLeft: 'auto' }}
              aria-label="删除会话"
              onClick={(e) => {
                e.stopPropagation();
                setDeleteTarget(s.id);
              }}
            >
              ×
            </button>
          )}
        </div>
      </div>
    </div>
  );

  const sessionList = (
    <aside className="session-list">
      <div className="session-list-header">
        <button
          type="button"
          className="btn btn-primary btn-block"
          data-testid="new-session-btn"
          onClick={() => void createSession()}
          disabled={manageMode}
        >
          新建对话
        </button>
        <div className="field mt-sm" style={{ height: 32 }}>
          <input
            placeholder="搜索会话..."
            value={sessionSearch}
            onChange={(e) => setSessionSearch(e.target.value)}
          />
        </div>
        <div className="session-manage-bar">
          {!manageMode ? (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setManageMode(true)}
            >
              批量管理
            </button>
          ) : (
            <>
              <button type="button" className="btn btn-ghost btn-sm" onClick={selectAllVisible}>
                全选
              </button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={clearSelection}>
                清空
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                style={{ color: 'var(--danger, #ff6b6b)' }}
                disabled={selectedIds.size === 0}
                onClick={() => setBatchDeleteIds([...selectedIds])}
              >
                删除 ({selectedIds.size})
              </button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={exitManage}>
                完成
              </button>
            </>
          )}
        </div>
      </div>

      <div className="session-list-body">
        <section className="session-section">
          <button
            type="button"
            className="session-section__head"
            onClick={() => setChatOpen((v) => !v)}
            aria-expanded={chatOpen}
          >
            <span className="session-section__label">
              <span className="session-section__dot session-section__dot--chat" />
              手动对话
            </span>
            <span className="session-section__meta">
              {chatSessions.length}
              <Chevron open={chatOpen} />
            </span>
          </button>
          {chatOpen && (
            <div className="session-section__body">
              {chatSessions.length === 0 ? (
                <p className="session-section__empty">暂无主动对话，点击上方新建</p>
              ) : (
                chatSessions.map((s) => renderSessionItem(s, 'chat'))
              )}
            </div>
          )}
        </section>

        <section className="session-section session-section--analyze">
          <button
            type="button"
            className="session-section__head"
            onClick={() => setAnalyzeOpen((v) => !v)}
            aria-expanded={analyzeOpen}
            disabled={analyzeSessions.length === 0}
          >
            <span className="session-section__label">
              <span className="session-section__dot session-section__dot--analyze" />
              快速分析
            </span>
            <span className="session-section__meta">
              {analyzeSessions.length}
              <Chevron open={analyzeOpen} />
            </span>
          </button>
          {analyzeOpen && (
            <div className="session-section__body">
              {analyzeSessions.length === 0 ? (
                <p className="session-section__empty">暂无快速分析记录</p>
              ) : (
                analyzeSessions.map((s) => renderSessionItem(s, 'analyze'))
              )}
            </div>
          )}
        </section>
      </div>

      <div
        className="session-list-header"
        style={{ borderTop: '1px solid var(--bg-300)', borderBottom: 0, padding: '10px 14px' }}
      >
        <Link
          to="/settings"
          className="btn btn-sm btn-ghost"
          style={{ justifyContent: 'flex-start', width: '100%', gap: 8 }}
        >
          Agent 配置
        </Link>
      </div>
    </aside>
  );

  return (
    <div className="chat-layout">
      {(sessionListOpen || contextPanelOpen) && (
        <div
          className="chat-drawer-backdrop"
          data-testid="chat-drawer-backdrop"
          onClick={() => {
            setSessionListOpen(false);
            setContextPanelOpen(false);
          }}
        />
      )}
      {sessionListOpen && sessionList}

      <main className="chat-area">
        <ChatPanel
          sessionListOpen={sessionListOpen}
          contextPanelOpen={contextPanelOpen}
          onToggleSessionList={() => setSessionListOpen((v) => !v)}
          onToggleContextPanel={() => setContextPanelOpen((v) => !v)}
        />
      </main>

      {contextPanelOpen && (
        <AgentContextSidebar
          sessionId={currentSessionId}
          toolLogOpen={toolLogOpen}
          onToggleToolLog={() => setToolLogOpen((v) => !v)}
          toolCalls={toolCalls}
        />
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="删除会话"
        message="确定删除此会话？"
        danger
        onConfirm={() => {
          if (deleteTarget) void deleteSession(deleteTarget);
          setDeleteTarget(null);
        }}
        onCancel={() => setDeleteTarget(null)}
      />

      <ConfirmDialog
        open={batchDeleteIds !== null}
        title="批量删除会话"
        message={`确定删除选中的 ${batchDeleteIds?.length ?? 0} 个会话？此操作不可撤销。`}
        danger
        onConfirm={() => {
          const ids = batchDeleteIds ?? [];
          setBatchDeleteIds(null);
          void (async () => {
            for (const id of ids) {
              await deleteSession(id);
            }
            exitManage();
          })();
        }}
        onCancel={() => setBatchDeleteIds(null)}
      />
    </div>
  );
}
