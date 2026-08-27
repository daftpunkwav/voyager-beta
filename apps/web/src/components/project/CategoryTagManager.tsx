/**
 * 分类 / 标签管理面板（项目库入口）
 */
import { useState } from 'react';
import type { Category, Tag } from '@/api/types';
import {
  useCreateCategory,
  useCreateTag,
  useDeleteCategory,
  useDeleteTag,
} from '@/hooks/useProjects';
import { useUIStore } from '@/stores/uiStore';

interface CategoryTagManagerProps {
  open: boolean;
  onClose: () => void;
  categories: Category[];
  tags: Tag[];
}

export function CategoryTagManager({
  open,
  onClose,
  categories,
  tags,
}: CategoryTagManagerProps) {
  const [tab, setTab] = useState<'categories' | 'tags'>('categories');
  const [name, setName] = useState('');
  const createCategory = useCreateCategory();
  const deleteCategory = useDeleteCategory();
  const createTag = useCreateTag();
  const deleteTag = useDeleteTag();
  const addToast = useUIStore((s) => s.addToast);

  if (!open) return null;

  const handleCreate = async () => {
    const n = name.trim();
    if (!n) return;
    try {
      if (tab === 'categories') {
        await createCategory.mutateAsync(n);
        addToast({ type: 'success', message: `已创建分类「${n}」` });
      } else {
        await createTag.mutateAsync(n);
        addToast({ type: 'success', message: `已创建标签「${n}」` });
      }
      setName('');
    } catch {
      addToast({ type: 'error', message: '创建失败（可能重名）' });
    }
  };

  const pending =
    createCategory.isPending ||
    createTag.isPending ||
    deleteCategory.isPending ||
    deleteTag.isPending;

  return (
    <div className="modal-overlay" role="presentation" onClick={onClose}>
      <div
        className="modal modal--wide edit-project-modal"
        role="dialog"
        aria-labelledby="cat-tag-mgr-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="edit-project-modal__head">
          <div>
            <h2 id="cat-tag-mgr-title">分类与标签</h2>
            <p className="muted small">管理项目筛选用的分类、标签</p>
          </div>
          <button type="button" className="chat-icon-btn" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </header>

        <div className="import-tabs" style={{ margin: '0 20px 12px' }}>
          <button
            type="button"
            className={`import-tab ${tab === 'categories' ? 'active' : ''}`}
            onClick={() => setTab('categories')}
          >
            分类 ({categories.length})
          </button>
          <button
            type="button"
            className={`import-tab ${tab === 'tags' ? 'active' : ''}`}
            onClick={() => setTab('tags')}
          >
            标签 ({tags.length})
          </button>
        </div>

        <div className="edit-project-modal__body">
          <div className="edit-project-new-tag">
            <input
              className="input"
              placeholder={tab === 'categories' ? '新建分类名称…' : '新建标签名称…'}
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  void handleCreate();
                }
              }}
            />
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={!name.trim() || pending}
              onClick={() => void handleCreate()}
            >
              创建
            </button>
          </div>

          <ul className="cat-tag-mgr-list">
            {tab === 'categories'
              ? categories.map((c) => (
                  <li key={c.id} className="cat-tag-mgr-item">
                    <span>
                      {c.icon ? `${c.icon} ` : ''}
                      {c.name}
                      {c.is_preset && (
                        <span className="badge" style={{ marginLeft: 8 }}>
                          预设
                        </span>
                      )}
                    </span>
                    {!c.is_preset && (
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        style={{ color: 'var(--error)' }}
                        disabled={pending}
                        onClick={() =>
                          void deleteCategory.mutateAsync(c.id).then(
                            () => addToast({ type: 'success', message: '已删除分类' }),
                            () => addToast({ type: 'error', message: '删除失败' }),
                          )
                        }
                      >
                        删除
                      </button>
                    )}
                  </li>
                ))
              : tags.map((t) => (
                  <li key={t.id} className="cat-tag-mgr-item">
                    <span>
                      {t.name}
                      <span className="muted small" style={{ marginLeft: 8 }}>
                        ×{t.count}
                      </span>
                    </span>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      style={{ color: 'var(--error)' }}
                      disabled={pending}
                      onClick={() =>
                        void deleteTag.mutateAsync(t.id).then(
                          () => addToast({ type: 'success', message: '已删除标签' }),
                          () => addToast({ type: 'error', message: '删除失败' }),
                        )
                      }
                    >
                      删除
                    </button>
                  </li>
                ))}
          </ul>
        </div>

        <footer className="edit-project-modal__foot">
          <button type="button" className="btn btn-primary" onClick={onClose}>
            完成
          </button>
        </footer>
      </div>
    </div>
  );
}
