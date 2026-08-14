/** 仓库详情抽屉:README 按需拉取 + 元数据编辑(分类/标签/进度/备注)+ 删除。 */

import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { callCapability } from '@/bridge/client';
import { type RepoSummary, useSourcesStore } from './sourcesStore';

export function RepoDetail({ repoId, onClose }: { repoId: string; onClose: () => void }) {
  const repos = useSourcesStore((s) => s.repos);
  const setMeta = useSourcesStore((s) => s.setMeta);
  const remove = useSourcesStore((s) => s.remove);
  const repo = repos.find((r) => r.id === repoId);
  const [readme, setReadme] = useState<string | null>(null);
  const [category, setCategory] = useState(repo?.category ?? '');
  const [tagsText, setTagsText] = useState((repo?.tags ?? []).join(', '));
  const [progress, setProgress] = useState(repo?.progress ?? 'none');
  const [note, setNote] = useState(repo?.note ?? '');
  const [confirmDelete, setConfirmDelete] = useState(false);

  // README 只在详情打开时拉(坑 2:列表页禁止批量)
  useEffect(() => {
    setReadme(null);
    callCapability<{ readme: string }>('sources', 'get_readme', { repo_id: repoId })
      .then((r) => setReadme(r.readme ?? ''))
      .catch(() => setReadme('(README 加载失败)'));
  }, [repoId]);

  if (!repo) return null;

  const flushMeta = () => {
    const tags = tagsText.split(/[,，]/).map((t) => t.trim()).filter(Boolean);
    void setMeta(repoId, {
      category: category.trim(),
      tags,
      progress,
      note,
    });
  };

  return (
    <div className="repo-detail__mask" onClick={onClose} role="presentation">
      <aside
        className="repo-detail"
        role="dialog"
        aria-label={`${repo.owner}/${repo.name}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="repo-detail__head">
          <a href={repo.url} target="_blank" rel="noreferrer" className="repo-detail__title">
            {repo.owner}/{repo.name}
          </a>
          <button type="button" className="btn" onClick={onClose}>
            关闭
          </button>
        </div>
        {repo.status === 'failed' && repo.error ? (
          <div className="setting-field__error small">克隆失败:{repo.error}</div>
        ) : null}
        {repo.local_path ? (
          <div className="small muted mono">{repo.local_path}</div>
        ) : null}

        <div className="repo-detail__meta">
          <label className="small">
            分类
            <input
              className="setting-input"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              onBlur={flushMeta}
            />
          </label>
          <label className="small">
            标签(逗号分隔)
            <input
              className="setting-input"
              value={tagsText}
              onChange={(e) => setTagsText(e.target.value)}
              onBlur={flushMeta}
            />
          </label>
          <label className="small">
            学习进度
            <select
              className="setting-input"
              value={progress}
              onChange={(e) => {
                setProgress(e.target.value);
                void setMeta(repoId, { progress: e.target.value });
              }}
            >
              <option value="none">未学</option>
              <option value="learning">在学</option>
              <option value="done">已学</option>
            </select>
          </label>
          <label className="small">
            备注
            <textarea
              className="setting-input"
              rows={2}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              onBlur={flushMeta}
            />
          </label>
        </div>

        <div className="repo-detail__readme chat-md">
          {readme === null ? (
            <div className="loading-spinner">
              <div className="spinner" />
            </div>
          ) : (
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
              {readme || '(无 README)'}
            </ReactMarkdown>
          )}
        </div>

        <div className="repo-detail__foot">
          {confirmDelete ? (
            <>
              <span className="small">删除仓库记录与本地克隆,不可恢复?</span>
              <button
                type="button"
                className="btn"
                onClick={() => {
                  void remove(repoId);
                  onClose();
                }}
              >
                确认删除
              </button>
              <button type="button" className="btn" onClick={() => setConfirmDelete(false)}>
                取消
              </button>
            </>
          ) : (
            <button type="button" className="btn" onClick={() => setConfirmDelete(true)}>
              删除仓库
            </button>
          )}
        </div>
      </aside>
    </div>
  );
}

export type { RepoSummary };
