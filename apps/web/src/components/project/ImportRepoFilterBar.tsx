/**
 * 导入 / Stars 同步列表的筛选工具栏
 */
import { GlassSelect } from '@/components/common/GlassSelect';
import {
  type ImportRepoFilterState,
  type ImportSortBy,
  type ImportStatusFilter,
} from '@/utils/importRepoFilter';

interface ImportRepoFilterBarProps {
  value: ImportRepoFilterState;
  onChange: (next: ImportRepoFilterState) => void;
  languages: string[];
  /** 统计文案，如「显示 12 / 共 80 · 未导入 50」 */
  summary?: string;
  /** 全选当前筛选中可导入项 */
  onSelectVisible?: () => void;
  /** 清空选择 */
  onClearSelection?: () => void;
  selectVisibleDisabled?: boolean;
  clearSelectionDisabled?: boolean;
}

const STATUS_OPTIONS: Array<{ value: ImportStatusFilter; label: string }> = [
  { value: 'not_imported', label: '未导入' },
  { value: 'imported', label: '已导入' },
  { value: 'all', label: '全部' },
];

const SORT_OPTIONS: Array<{ value: ImportSortBy; label: string }> = [
  { value: 'stars', label: 'Stars 高→低' },
  { value: 'name', label: '名称 A→Z' },
  { value: 'language', label: '按语言' },
];

export function ImportRepoFilterBar({
  value,
  onChange,
  languages,
  summary,
  onSelectVisible,
  onClearSelection,
  selectVisibleDisabled,
  clearSelectionDisabled,
}: ImportRepoFilterBarProps) {
  const languageOptions = [
    { value: '', label: '全部语言' },
    ...languages.map((l) => ({ value: l, label: l })),
  ];

  const patch = (partial: Partial<ImportRepoFilterState>) =>
    onChange({ ...value, ...partial });

  return (
    <div className="import-repo-filters">
      <div className="import-repo-filters__row">
        <label className="import-repo-filters__search">
          <input
            type="search"
            className="input"
            aria-label="搜索仓库"
            placeholder="搜索 owner / 仓库 / 描述…"
            value={value.query}
            onChange={(e) => patch({ query: e.target.value })}
          />
        </label>
        <GlassSelect
          size="sm"
          aria-label="导入状态"
          value={value.importStatus}
          options={STATUS_OPTIONS}
          onChange={(v) => patch({ importStatus: v as ImportStatusFilter })}
        />
        <GlassSelect
          size="sm"
          aria-label="语言"
          value={value.language}
          options={languageOptions}
          onChange={(v) => patch({ language: v })}
        />
        <GlassSelect
          size="sm"
          aria-label="排序"
          value={value.sortBy}
          options={SORT_OPTIONS}
          onChange={(v) => patch({ sortBy: v as ImportSortBy })}
        />
      </div>
      <div className="import-repo-filters__meta">
        {summary && <span className="muted small">{summary}</span>}
        <div className="import-repo-filters__actions">
          {onSelectVisible && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={selectVisibleDisabled}
              onClick={onSelectVisible}
            >
              全选当前
            </button>
          )}
          {onClearSelection && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={clearSelectionDisabled}
              onClick={onClearSelection}
            >
              清空选择
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
