/** 笔记工作区顶栏:视图 / 字号 / 关联 / 保存态 / 更多。展示层,不直接打能力。 */

import { useEffect, useRef, useState } from 'react';
import { GlassSelect } from '@/components/common/GlassSelect';
import { NOTES_FONT_MAX, NOTES_FONT_MIN, type NotesMode } from './noteUtils';

interface NotesWorkspaceBarProps {
  mode: NotesMode;
  fontSize: number;
  saveState: 'saved' | 'unsaved' | 'saving';
  persisted: boolean;
  pinned: boolean;
  archived: boolean;
  projectId: string;
  projectOptions: { value: string; label: string }[];
  scribeStreaming: boolean;
  syncScroll: boolean;
  onBack: () => void;
  onNew: () => void;
  onMode: (mode: NotesMode) => void;
  onBumpFont: (delta: number) => void;
  onProject: (id: string) => void;
  onTogglePin: () => void;
  onToggleArchive: () => void;
  onToggleSync: () => void;
  onScribe: () => void;
  onVersions: () => void;
  onExport: () => void;
  onDelete: () => void;
  onTrash: () => void;
}

export function NotesWorkspaceBar({
  mode,
  fontSize,
  saveState,
  persisted,
  pinned,
  archived,
  projectId,
  projectOptions,
  scribeStreaming,
  syncScroll,
  onBack,
  onNew,
  onMode,
  onBumpFont,
  onProject,
  onTogglePin,
  onToggleArchive,
  onToggleSync,
  onScribe,
  onVersions,
  onExport,
  onDelete,
  onTrash,
}: NotesWorkspaceBarProps) {
  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!moreOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) setMoreOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMoreOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [moreOpen]);

  return (
    <header className="notes-topbar">
      <button type="button" className="topbar-action" aria-label="返回列表" onClick={onBack}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={16} height={16} aria-hidden>
          <path d="M15 6l-6 6 6 6" />
        </svg>
      </button>
      <button type="button" className="btn btn-primary btn-sm" onClick={onNew}>
        新建
      </button>
      <div className="view-toggle" role="group" aria-label="展现形式">
        {(['edit', 'preview', 'split'] as const).map((m) => (
          <button
            key={m}
            type="button"
            data-testid={`notes-mode-${m}`}
            className={`view-btn${mode === m ? ' active' : ''}`}
            aria-pressed={mode === m}
            onClick={() => onMode(m)}
          >
            {m === 'edit' ? '编辑' : m === 'preview' ? '预览' : '分栏'}
          </button>
        ))}
      </div>
      <div className="notes-font-ctrl" role="group" aria-label="正文字号" data-testid="notes-font-ctrl">
        <button
          type="button"
          className="notes-font-btn"
          disabled={fontSize <= NOTES_FONT_MIN}
          aria-label="减小字号"
          onClick={() => onBumpFont(-1)}
        >
          A−
        </button>
        <span className="notes-font-val">{fontSize}</span>
        <button
          type="button"
          className="notes-font-btn"
          disabled={fontSize >= NOTES_FONT_MAX}
          aria-label="增大字号"
          onClick={() => onBumpFont(1)}
        >
          A+
        </button>
      </div>
      {mode === 'split' && (
        <button
          type="button"
          className={`btn btn-sm notes-sync-btn${syncScroll ? ' is-on' : ''}`}
          data-testid="notes-sync-scroll"
          aria-pressed={syncScroll}
          onClick={onToggleSync}
        >
          同步滚动
        </button>
      )}
      <GlassSelect
        size="sm"
        aria-label="关联项目"
        value={projectId}
        options={[{ value: '', label: '不关联项目' }, ...projectOptions]}
        onChange={onProject}
      />
      <div className="notes-topbar-spacer" />
      <div className={`save-indicator ${saveState}`}>
        <span className="dot" />
        <span>{saveState === 'saved' ? '已保存' : saveState === 'saving' ? '保存中' : '未保存'}</span>
      </div>
      {persisted && (
        <button
          type="button"
          className={`topbar-action${pinned ? ' is-on' : ''}`}
          aria-pressed={pinned}
          aria-label={pinned ? '取消置顶' : '置顶'}
          data-testid="notes-pin-btn"
          onClick={onTogglePin}
        >
          <svg viewBox="0 0 24 24" fill={pinned ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" width={16} height={16} aria-hidden>
            <path d="M12 17v5M8 3h8l-1 7h3l-6 7-6-7h3L8 3z" />
          </svg>
        </button>
      )}
      <div className="notes-more" ref={moreRef}>
        <button
          type="button"
          className={`topbar-action${moreOpen ? ' is-on' : ''}`}
          aria-label="更多"
          aria-expanded={moreOpen}
          onClick={() => setMoreOpen((v) => !v)}
        >
          <svg viewBox="0 0 24 24" fill="currentColor" width={16} height={16} aria-hidden>
            <circle cx="6" cy="12" r="1.6" />
            <circle cx="12" cy="12" r="1.6" />
            <circle cx="18" cy="12" r="1.6" />
          </svg>
        </button>
        {moreOpen && (
          <div className="notes-more-menu" role="menu">
            <button
              type="button"
              role="menuitem"
              disabled={scribeStreaming}
              onClick={() => {
                setMoreOpen(false);
                onScribe();
              }}
            >
              {scribeStreaming ? 'Miyai 生成中…' : 'Miyai 辅助'}
            </button>
            {persisted && (
              <>
                <button type="button" role="menuitem" onClick={() => { setMoreOpen(false); onVersions(); }}>
                  版本历史
                </button>
                <button type="button" role="menuitem" onClick={() => { setMoreOpen(false); onExport(); }}>
                  导出 Markdown
                </button>
                <button type="button" role="menuitem" onClick={() => { setMoreOpen(false); onToggleArchive(); }}>
                  {archived ? '取消归档' : '归档'}
                </button>
                <button type="button" role="menuitem" className="is-danger" onClick={() => { setMoreOpen(false); onDelete(); }}>
                  移入回收站
                </button>
              </>
            )}
            <button type="button" role="menuitem" onClick={() => { setMoreOpen(false); onTrash(); }}>
              回收站
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
