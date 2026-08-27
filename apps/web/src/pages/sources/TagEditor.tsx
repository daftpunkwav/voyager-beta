/** 资源标签行内编辑:chips 展示 + 回车添加 + × 删除。
 *
 * 供 DocReader / PageReader 等资源详情页复用;保存由调用方经 onChange
 * 落到对应 set_*_meta 能力(受控组件,不自行发请求)。
 */
import { useState } from 'react';

interface TagEditorProps {
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
}

export function TagEditor({ tags, onChange, placeholder = '添加标签后回车' }: TagEditorProps) {
  const [draft, setDraft] = useState('');

  const add = () => {
    const t = draft.trim();
    if (!t) return;
    if (!tags.includes(t)) onChange([...tags, t]);
    setDraft('');
  };

  const remove = (tag: string) => {
    onChange(tags.filter((x) => x !== tag));
  };

  return (
    <div className="tag-editor" role="group" aria-label="资源标签">
      {tags.map((t) => (
        <span key={t} className="tag-editor__chip">
          {t}
          <button
            type="button"
            className="tag-editor__remove"
            aria-label={`移除标签 ${t}`}
            onClick={() => remove(t)}
          >
            ×
          </button>
        </span>
      ))}
      <input
        className="tag-editor__input"
        value={draft}
        placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            add();
          }
        }}
        onBlur={add}
      />
    </div>
  );
}
