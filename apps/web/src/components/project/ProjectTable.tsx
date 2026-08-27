import { useNavigate } from 'react-router-dom';
import type { ChangeEvent } from 'react';
import type { Category, Project, Tag } from '@/api/types';
import { ProgressBadge } from './ProgressBadge';
import { categoryCssClass, categoryLabel } from '@/utils/labels';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import {
  formatNumber,
  langCssClass,
  REPO_AVATAR_GRADIENTS,
  splitRepoName,
} from '@/utils/format';
import { useProjectStore } from '@/stores/projectStore';

interface ProjectTableProps {
  projects: Project[];
  tags: Tag[];
  categories?: Category[];
  onImportClick?: () => void;
}

export function ProjectTable({
  projects,
  tags,
  categories = [],
  onImportClick,
}: ProjectTableProps) {
  const navigate = useNavigate();
  const tagMap = new Map(tags.map((t) => [t.id, t.name]));

  const selectedIds = useProjectStore((s) => s.selectedIds);
  const toggleSelected = useProjectStore((s) => s.toggleSelected);
  const setSelected = useProjectStore((s) => s.setSelected);

  const pageIds = projects.map((p) => p.id);
  const selectedSet = new Set(selectedIds);
  const allOnPageSelected =
    pageIds.length > 0 && pageIds.every((id) => selectedSet.has(id));
  const someOnPageSelected =
    pageIds.some((id) => selectedSet.has(id)) && !allOnPageSelected;

  const handleHeaderToggle = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.checked) {
      // 全选当前页：合并并去重
      const next = new Set(selectedIds);
      pageIds.forEach((id) => next.add(id));
      setSelected(Array.from(next));
    } else {
      // 取消选中当前页
      const pageSet = new Set(pageIds);
      setSelected(selectedIds.filter((id) => !pageSet.has(id)));
    }
  };

  if (projects.length === 0) {
    return (
      <div id="table-wrap" data-testid="project-table">
        <EmptyState
          title="还没有项目入库"
          description="从 GitHub 同步 Stars，或者粘贴仓库地址开始你的第一个项目。"
          icon={EmptyStateIcons.library}
          action={
            <>
              <button
                type="button"
                className="btn btn-primary"
                data-testid="empty-import-stars-btn"
                onClick={onImportClick}
              >
                同步 GitHub Stars
              </button>
              <button
                type="button"
                className="btn glass-card glass-card--control liquid-glass--pill liquid-glass--interactive"
                onClick={onImportClick}
              >
                粘贴 URL 导入
              </button>
            </>
          }
        />
      </div>
    );
  }

  return (
    <div id="table-wrap" data-testid="project-table">
      <table className="table">
        <thead>
          <tr>
            <th className="col-check">
              <span className="th-checkbox">
                <input
                  type="checkbox"
                  className="checkbox"
                  aria-label="全选当前页"
                  data-testid="projects-select-all"
                  checked={allOnPageSelected}
                  ref={(el) => {
                    if (el) el.indeterminate = someOnPageSelected;
                  }}
                  onChange={handleHeaderToggle}
                />
              </span>
            </th>
            <th>仓库</th>
            <th>分类</th>
            <th>语言</th>
            <th>Stars</th>
            <th>进度</th>
            <th>标签</th>
            <th className="col-actions">操作</th>
          </tr>
        </thead>
        <tbody>
          {projects.map((p, i) => {
            const { owner, repo } = splitRepoName(p.name);
            const catCls = categoryCssClass(p.category_id, categories);
            const isSelected = selectedSet.has(p.id);
            return (
              <tr
                key={p.id}
                data-project-id={p.id}
                data-testid={`project-row-${p.id}`}
                className={isSelected ? 'is-selected' : undefined}
                onClick={() => navigate(`/projects/${p.id}`)}
              >
                <td className="col-check" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    className="checkbox"
                    aria-label={`选择 ${p.name}`}
                    data-testid={`projects-row-check-${p.id}`}
                    checked={isSelected}
                    onChange={() => toggleSelected(p.id)}
                  />
                </td>
                <td>
                  <div className="repo-cell">
                    <div
                      className="repo-avatar"
                      style={{
                        background: REPO_AVATAR_GRADIENTS[i % REPO_AVATAR_GRADIENTS.length],
                      }}
                    >
                      {(repo[0] ?? '?').toUpperCase()}
                    </div>
                    <div className="repo-info">
                      <div className="repo-name">
                        <span className="owner">{owner}</span>
                        <span className="slash">/</span>
                        <span>{repo}</span>
                      </div>
                      <div className="repo-desc">{p.description ?? ''}</div>
                    </div>
                  </div>
                </td>
                <td>
                  <span className={`badge ${catCls}`}>
                    {categoryLabel(p.category_id, categories)}
                  </span>
                </td>
                <td>
                  <span className={`lang-dot ${langCssClass(p.language)}`}>
                    {p.language ?? '-'}
                  </span>
                </td>
                <td>
                  <span className="stars">★ {formatNumber(p.stars)}</span>
                </td>
                <td>
                  <ProgressBadge progress={p.progress} />
                </td>
                <td>
                  <div className="tags">
                    {p.tags?.slice(0, 2).map((tid) => (
                      <span key={tid} className="tag">
                        {tagMap.get(tid) ?? tid.replace(/^tag_/, '')}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="col-actions" onClick={(e) => e.stopPropagation()}>
                  <div className="row-actions">
                    <button
                      type="button"
                      className="btn-scout"
                      onClick={() => navigate(`/projects/${p.id}`)}
                    >
                      Scout
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
