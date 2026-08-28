import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getApi } from '@/api/client';
import { classifyErrorKind } from '@/components/graph/l0EdgeTypes';

type IndexMode = 'fast' | 'moderate' | 'full';

type IndexRow = {
  project_id: string;
  status: string;
  error?: string | null;
  error_kind?: string | null;
  index_mode?: string;
  node_count?: number | null;
  engine_project?: string;
};

type TabId = 'ready' | 'running' | 'failed';

const ACTIVE = new Set(['QUEUED', 'CLONING', 'INDEXING']);
const FAILED = new Set(['CLONE_FAILED', 'INDEX_FAILED']);

const STATUS_LABEL: Record<string, string> = {
  QUEUED: '排队中',
  CLONING: '克隆中',
  INDEXING: '索引中',
  READY: '已就绪',
  CLONE_FAILED: '克隆失败',
  INDEX_FAILED: '索引失败',
};

const MODE_OPTIONS: { id: IndexMode; label: string }[] = [
  { id: 'fast', label: '快速' },
  { id: 'moderate', label: '标准' },
  { id: 'full', label: '完整' },
];

function shortId(id: string): string {
  return id.length > 10 ? `${id.slice(0, 8)}…` : id;
}

function ModeMenu({
  disabled,
  onPick,
  label = '重新索引',
}: {
  disabled?: boolean;
  onPick: (mode: IndexMode) => void;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="graph-index-modal__menu">
      <button
        type="button"
        disabled={disabled}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {label}
      </button>
      {open && (
        <div className="graph-index-modal__menu-panel" role="menu">
          {MODE_OPTIONS.map((m) => (
            <button
              key={m.id}
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onPick(m.id);
              }}
            >
              {m.label}
              <span className="muted">{m.id}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function FailedRow({
  row,
  label,
  onRetry,
  onDelete,
  busy,
}: {
  row: IndexRow;
  label: string;
  onRetry: (mode: IndexMode) => void;
  onDelete: () => void;
  busy?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const kind = classifyErrorKind(row.error_kind, row.error);
  const detail =
    row.error?.trim() || '无详细错误信息（可能是克隆目录冲突或进程中断）';

  return (
    <li className="graph-index-modal__row is-failed">
      <div className="graph-index-modal__row-main">
        <strong>{label}</strong>
        <span className="graph-index-modal__phase">
          {STATUS_LABEL[row.status] || row.status}
          {row.index_mode ? ` · ${row.index_mode}` : ''}
        </span>
        <button
          type="button"
          className="graph-index-modal__err-toggle"
          aria-expanded={expanded}
          onClick={() => setExpanded((v) => !v)}
        >
          {kind}
          <span>{expanded ? '收起原因' : '展开原因'}</span>
        </button>
        {expanded && (
          <pre className="graph-index-modal__err" title={detail}>
            {detail}
          </pre>
        )}
      </div>
      <div className="graph-index-modal__actions">
        <ModeMenu disabled={busy} label="重试" onPick={onRetry} />
        <button
          type="button"
          className="is-danger"
          disabled={busy}
          onClick={onDelete}
        >
          删除
        </button>
      </div>
    </li>
  );
}

/** 索引详细：紧凑入口 + 三页签弹窗（成功 / 进行中 / 失败） */
export function GraphIndexProgressBar() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<TabId>('ready');

  const q = useQuery({
    queryKey: ['graph-index-statuses'],
    queryFn: () => getApi().listCodeGraphIndexStatuses(),
    refetchInterval: (query) => {
      const items = query.state.data?.data?.items as IndexRow[] | undefined;
      const running = items?.some((i) => ACTIVE.has(i.status));
      return running ? 2000 : 15_000;
    },
  });

  const graphQ = useQuery({
    queryKey: ['graph-index-name-map'],
    queryFn: async () => {
      const res = await getApi().getGraph({ max_edges: 1 });
      return res.data?.nodes || [];
    },
    staleTime: 60_000,
  });

  const nameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const n of graphQ.data || []) {
      map.set(n.id, n.name);
    }
    return map;
  }, [graphQ.data]);

  const labelOf = (row: IndexRow) =>
    nameById.get(row.project_id) || row.engine_project || shortId(row.project_id);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['graph-index-statuses'] });
    void qc.invalidateQueries({ queryKey: ['code-graph'] });
    void qc.invalidateQueries({ queryKey: ['graph-index-status'] });
  };

  const cancel = useMutation({
    mutationFn: (projectId: string) => getApi().cancelCodeGraphIndex(projectId),
    onSuccess: invalidate,
  });

  const del = useMutation({
    mutationFn: (projectId: string) => getApi().deleteCodeGraphIndex(projectId),
    onSuccess: invalidate,
  });

  const reindex = useMutation({
    mutationFn: ({ projectId, mode }: { projectId: string; mode: IndexMode }) =>
      getApi().triggerCodeGraphIndex(projectId, { mode }),
    onSuccess: invalidate,
  });

  const busy = cancel.isPending || del.isPending || reindex.isPending;

  const confirmDelete = (row: IndexRow, label: string) => {
    const ok = window.confirm(
      `删除「${label}」的索引？\n将清理本地克隆缓存与图谱数据库，不可恢复。`,
    );
    if (ok) del.mutate(row.project_id);
  };

  const items = useMemo(
    () => (q.data?.data?.items || []) as IndexRow[],
    [q.data?.data?.items],
  );
  const stats = q.data?.data?.stats;

  const running = useMemo(() => items.filter((i) => ACTIVE.has(i.status)), [items]);
  const failed = useMemo(() => items.filter((i) => FAILED.has(i.status)), [items]);
  const ready = useMemo(() => items.filter((i) => i.status === 'READY'), [items]);
  const readyCount = stats?.ready ?? ready.length;
  const failedCount = stats?.failed ?? failed.length;

  const tabs: { id: TabId; label: string; count: number; tone: string }[] = [
    { id: 'ready', label: '已索引', count: readyCount, tone: 'ok' },
    { id: 'running', label: '进行中', count: running.length, tone: 'run' },
    { id: 'failed', label: '失败', count: failedCount, tone: 'fail' },
  ];

  const list = tab === 'ready' ? ready : tab === 'running' ? running : failed;

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const modal =
    open &&
    createPortal(
      <div
        className="graph-index-modal-backdrop"
        role="presentation"
        onClick={() => setOpen(false)}
      >
        <div
          className="graph-index-modal glass-card glass-card--dialog"
          role="dialog"
          aria-modal="true"
          aria-label="索引详细"
          onClick={(e) => e.stopPropagation()}
        >
          <header className="graph-index-modal__head">
            <h2>索引详细</h2>
            <button
              type="button"
              className="graph-index-modal__close"
              onClick={() => setOpen(false)}
              aria-label="关闭"
            >
              ×
            </button>
          </header>

          <div className="graph-index-modal__tabs" role="tablist">
            {tabs.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                className={`graph-index-modal__tab${tab === t.id ? ' is-active' : ''}`}
                onClick={() => setTab(t.id)}
              >
                <span className={`graph-index-modal__circle is-${t.tone}`}>{t.count}</span>
                <span>{t.label}</span>
              </button>
            ))}
          </div>

          <div className="graph-index-modal__body" role="tabpanel">
            {q.isLoading && <p className="graph-index-modal__empty">加载中…</p>}
            {!q.isLoading && list.length === 0 && (
              <p className="graph-index-modal__empty">
                {tab === 'ready' && '暂无已就绪的索引'}
                {tab === 'running' && '当前没有进行中的任务'}
                {tab === 'failed' && '没有失败记录'}
              </p>
            )}
            <ul className="graph-index-modal__list">
              {list.map((row) => {
                const label = labelOf(row);
                if (tab === 'failed') {
                  return (
                    <FailedRow
                      key={row.project_id}
                      row={row}
                      label={label}
                      busy={busy}
                      onRetry={(mode) =>
                        reindex.mutate({ projectId: row.project_id, mode })
                      }
                      onDelete={() => confirmDelete(row, label)}
                    />
                  );
                }
                return (
                  <li key={row.project_id} className={`graph-index-modal__row is-${tab}`}>
                    <div className="graph-index-modal__row-main">
                      <strong>{label}</strong>
                      <span className="graph-index-modal__phase">
                        {STATUS_LABEL[row.status] || row.status}
                        {row.index_mode ? ` · ${row.index_mode}` : ''}
                        {row.node_count != null ? ` · ${row.node_count} 节点` : ''}
                      </span>
                    </div>
                    <div className="graph-index-modal__actions">
                      {tab === 'running' && (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => cancel.mutate(row.project_id)}
                        >
                          取消
                        </button>
                      )}
                      {tab === 'ready' && (
                        <>
                          <ModeMenu
                            disabled={busy}
                            label="重新索引"
                            onPick={(mode) =>
                              reindex.mutate({ projectId: row.project_id, mode })
                            }
                          />
                          <button
                            type="button"
                            className="is-danger"
                            disabled={busy}
                            onClick={() => confirmDelete(row, label)}
                          >
                            删除
                          </button>
                        </>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      </div>,
      document.body,
    );

  return (
    <>
      <button
        type="button"
        className="graph-index-trigger"
        onClick={() => {
          setOpen(true);
          /* 默认打开「已索引」；若无成功再回落到进行中 / 失败 */
          setTab(
            readyCount > 0 ? 'ready' : running.length ? 'running' : failedCount ? 'failed' : 'ready',
          );
        }}
        title="打开索引详细"
      >
        <span className="graph-index-trigger__label">索引详细</span>
        <span className="graph-index-trigger__badge is-ok" title="已索引">
          {readyCount}
        </span>
        <span className="graph-index-trigger__badge is-run" title="进行中">
          {running.length}
        </span>
        <span className="graph-index-trigger__badge is-fail" title="失败">
          {failedCount}
        </span>
      </button>
      {modal}
    </>
  );
}
