/**
 * 编辑项目：分类 + 标签
 */
import { useEffect, useState } from 'react';
import type { Category, Project, Tag } from '@/api/types';
import {
  useCreateTag,
  useSetProjectTags,
  useUpdateProject,
} from '@/hooks/useProjects';
import { useUIStore } from '@/stores/uiStore';
import { GlassSelect } from '@/components/common/GlassSelect';

interface EditProjectModalProps {
  open: boolean;
  project: Project;
  categories: Category[];
  tags: Tag[];
  onClose: () => void;
}

export function EditProjectModal({
  open,
  project,
  categories,
  tags,
  onClose,
}: EditProjectModalProps) {
  const [categoryId, setCategoryId] = useState(project.category_id ?? '');
  const [selectedTags, setSelectedTags] = useState<Set<string>>(
    new Set(project.tags ?? []),
  );
  const [newTag, setNewTag] = useState('');
  const updateProject = useUpdateProject();
  const setProjectTags = useSetProjectTags();
  const createTag = useCreateTag();
  const addToast = useUIStore((s) => s.addToast);

  useEffect(() => {
    if (!open) return;
    setCategoryId(project.category_id ?? '');
    setSelectedTags(new Set(project.tags ?? []));
    setNewTag('');
  }, [open, project]);

  if (!open) return null;

  const categoryOptions = [
    { value: '', label: '未分类' },
    ...categories.map((c) => ({
      value: c.id,
      label: c.is_preset ? `${c.name}（预设）` : c.name,
    })),
  ];

  const toggleTag = (id: string) => {
    setSelectedTags((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleAddTag = async () => {
    const name = newTag.trim();
    if (!name) return;
    try {
      const tag = await createTag.mutateAsync(name);
      setSelectedTags((prev) => new Set(prev).add(tag.id));
      setNewTag('');
      addToast({ type: 'success', message: `已创建标签 ${tag.name}` });
    } catch {
      addToast({ type: 'error', message: '创建标签失败' });
    }
  };

  const handleSave = async () => {
    try {
      await updateProject.mutateAsync({
        id: project.id,
        data: {
          // 空字符串表示清空分类（后端 Optional UUID = null）
          category_id: (categoryId || null) as unknown as string,
        },
      });
      await setProjectTags.mutateAsync({
        projectId: project.id,
        tagIds: [...selectedTags],
      });
      addToast({ type: 'success', message: '项目分类与标签已更新' });
      onClose();
    } catch {
      addToast({ type: 'error', message: '保存失败' });
    }
  };

  const pending =
    updateProject.isPending || setProjectTags.isPending || createTag.isPending;

  return (
    <div className="modal-overlay" role="presentation" onClick={onClose}>
      <div
        className="modal modal--wide edit-project-modal"
        role="dialog"
        aria-labelledby="edit-project-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="edit-project-modal__head">
          <div>
            <h2 id="edit-project-title">编辑项目</h2>
            <p className="muted small mono">{project.name}</p>
          </div>
          <button type="button" className="chat-icon-btn" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </header>

        <div className="edit-project-modal__body">
          <label className="edit-project-field">
            <span className="label">分类</span>
            <GlassSelect
              aria-label="项目分类"
              value={categoryId}
              options={categoryOptions}
              onChange={setCategoryId}
            />
          </label>

          <div className="edit-project-field">
            <span className="label">标签</span>
            <div className="edit-project-tags">
              {tags.length === 0 && (
                <span className="muted small">暂无标签，可在下方新建</span>
              )}
              {tags.map((t) => {
                const on = selectedTags.has(t.id);
                return (
                  <button
                    key={t.id}
                    type="button"
                    className={`edit-tag-chip ${on ? 'is-on' : ''}`}
                    onClick={() => toggleTag(t.id)}
                  >
                    {t.name}
                    {typeof t.count === 'number' && t.count > 0 ? (
                      <span className="edit-tag-chip__count">{t.count}</span>
                    ) : null}
                  </button>
                );
              })}
            </div>
            <div className="edit-project-new-tag">
              <input
                className="input"
                placeholder="新建标签…"
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    void handleAddTag();
                  }
                }}
              />
              <button
                type="button"
                className="btn btn-sm"
                disabled={!newTag.trim() || createTag.isPending}
                onClick={() => void handleAddTag()}
              >
                添加
              </button>
            </div>
          </div>
        </div>

        <footer className="edit-project-modal__foot">
          <button type="button" className="btn" onClick={onClose} disabled={pending}>
            取消
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={pending}
            onClick={() => void handleSave()}
          >
            {pending ? '保存中…' : '保存'}
          </button>
        </footer>
      </div>
    </div>
  );
}
