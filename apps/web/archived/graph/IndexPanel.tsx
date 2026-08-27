/** 索引队列面板:enqueue 表单(项目名/资源库仓库选择)、jobs 列表、
 * cancel / reorder(上移)、引擎徽标(C/Python 回退,诚实显示不标红,坑 5)、
 * task.progress 进度条(经 props 注入,订阅在页面层)。
 */

import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { type IndexJob, useGraphStore } from './graphStore';

export interface JobProgress {
  progress: number;
  stage: string;
}

export function EngineBadge() {
  const engine = useGraphStore((s) => s.engine);
  if (!engine) return null;
  const text = engine.engine === 'c'
    ? 'C 引擎'
    : engine.fallback ? 'Python 引擎(回退)' : 'Python 引擎';
  return (
    <span
      className={`setting-badge ${engine.engine === 'python' ? 'setting-badge--none' : 'setting-badge--ok'}`}
      title="引擎回退是设计内降级(决策 6),功能照常"
    >
      {text}
    </span>
  );
}

export function IndexPanel({
  onClose,
  progress,
}: {
  onClose: () => void;
  progress: Record<string, JobProgress>;
}) {
  const { project, projects, repos, loadRepos } = useGraphStore();
  const [jobs, setJobs] = useState<IndexJob[]>([]);
  const [repoIdx, setRepoIdx] = useState('');
  const [manualProject, setManualProject] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const refreshJobs = async () => {
    try {
      setJobs(await callCapability<IndexJob[]>('graph', 'list_index_jobs'));
    } catch {
      // 面板打开期间列表拉取失败静默(下次动作后再试)
    }
  };

  useEffect(() => {
    void refreshJobs();
    void loadRepos();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const enqueue = async () => {
    setBusy(true);
    setError('');
    try {
      let proj = manualProject.trim();
      let repoPath = '';
      const picked = repoIdx !== '' ? repos[Number(repoIdx)] : undefined;
      if (picked) {
        // 项目名取 owner__name(与资源库克隆目录一致);手填项目名优先
        proj = proj || picked.name.replace('/', '__');
        repoPath = picked.local_path;
      } else if (proj) {
        repoPath = `workspace/repo/${proj}`;
      }
      if (!proj || !repoPath) {
        setError('需要选择资源库仓库,或手填项目名(repo_path 默认 workspace/repo/<项目名>)');
        return;
      }
      await callCapability('graph', 'enqueue_index', { project: proj, repo_path: repoPath });
      if (!projects.includes(proj)) {
        // 新项目立即进入选择器
        useGraphStore.setState({ projects: [...projects, proj] });
      }
      await refreshJobs();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const cancel = async (jobId: string) => {
    await callCapability('graph', 'cancel_index', { job_id: jobId }).catch(() => {});
    await refreshJobs();
  };

  const moveUp = async (jobId: string) => {
    const queued = jobs.filter((j) => j.status === 'queued');
    const idx = queued.findIndex((j) => j.id === jobId);
    const above = idx > 0 ? queued[idx - 1] : undefined;
    if (idx <= 0 || !above) return;
    // 目标优先级 = 前一个任务减一(数值小者优先),实现"插队到它前面"
    await callCapability('graph', 'reorder_queue', {
      job_id: jobId,
      priority: Math.max(0, above.priority - 1),
    }).catch(() => {});
    await refreshJobs();
  };

  const stageText = (j: IndexJob): string => {
    const p = progress[j.id];
    if (p) return `${Math.round(p.progress * 100)}% ${p.stage}`;
    return j.error ? j.error.slice(0, 80) : '';
  };

  const active = jobs.filter((j) => j.status === 'queued' || j.status === 'running');
  const finished = jobs.filter((j) => j.status !== 'queued' && j.status !== 'running');

  const row = (j: IndexJob, canMove: boolean) => (
    <div key={j.id} className={`index-job index-job--${j.status}`}>
      <span className="index-job__project mono">{j.project}</span>
      <span className={`setting-badge ${
        j.status === 'done' ? 'setting-badge--ok'
          : j.status === 'failed' ? 'repo-badge--failed'
            : 'setting-badge--none'}`}>
        {{ queued: '排队', running: '索引中', done: '完成', failed: '失败',
           cancelled: '已取消' }[j.status]}
      </span>
      {j.status === 'running' && progress[j.id] ? (
        <div className="chat-card__bar">
          <div
            className="chat-card__fill"
            style={{ width: `${Math.round((progress[j.id]?.progress ?? 0) * 100)}%` }}
          />
        </div>
      ) : null}
      {stageText(j) ? <div className="small muted">{stageText(j)}</div> : null}
      <div className="index-job__actions">
        {j.status === 'queued' && canMove ? (
          <button type="button" className="btn btn-sm" onClick={() => void moveUp(j.id)}>
            上移
          </button>
        ) : null}
        {j.status === 'queued' ? (
          <button type="button" className="btn btn-sm" onClick={() => void cancel(j.id)}>
            取消
          </button>
        ) : null}
        {j.status === 'done' && projects.includes(j.project) && j.project !== project ? (
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => useGraphStore.getState().setProject(j.project)}
          >
            查看
          </button>
        ) : null}
      </div>
    </div>
  );

  return (
    <div className="index-panel">
      <div className="node-editor__tabs">
        <span className="label">索引队列</span>
        <span className="sources-toolbar__spacer" />
        <EngineBadge />
        <button type="button" className="btn btn-sm" onClick={onClose}>
          关闭
        </button>
      </div>

      <div className="index-panel__form">
        <select
          className="setting-input"
          value={repoIdx}
          onChange={(e) => setRepoIdx(e.target.value)}
        >
          <option value="">-- 资源库仓库 --</option>
          {repos.map((r, i) => (
            <option key={r.local_path} value={i}>{r.name}</option>
          ))}
        </select>
        <input
          className="setting-input"
          value={manualProject}
          placeholder={repoIdx === '' ? '项目名(手动建图路径 workspace/repo/<名>)' : '项目名(默认仓库名)'}
          onChange={(e) => setManualProject(e.target.value)}
        />
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy || (repoIdx === '' && manualProject.trim() === '')}
          onClick={() => void enqueue()}
        >
          {busy ? '入队中…' : '入队索引'}
        </button>
      </div>
      {error ? <div className="setting-field__error small">{error}</div> : null}

      {active.length > 0 ? (
        <>
          <div className="label">进行中 / 排队({active.length})</div>
          {active.map((j, i) => row(j, i > 0))}
        </>
      ) : (
        <div className="small muted">队列为空:入队一个仓库开始建图。</div>
      )}

      {finished.length > 0 ? (
        <>
          <div className="label">历史({finished.length})</div>
          <div className="index-panel__history">
            {finished.slice(0, 20).map((j) => row(j, false))}
          </div>
        </>
      ) : null}
    </div>
  );
}
