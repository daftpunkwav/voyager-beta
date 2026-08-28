/** 工作区目录:大纲来自当前正文(未保存也更新);点击由页面决定跳编辑行或预览锚点。 */

import GithubSlugger from 'github-slugger';
import { tocHeadingLabel, type NoteTocItem } from './noteOutline';

export function TocPanel({
  items,
  onJump,
}: {
  items: NoteTocItem[];
  onJump: (item: NoteTocItem, headingId: string) => void;
}) {
  if (items.length === 0) return null;
  const slugs = new GithubSlugger();
  return (
    <nav className="toc-panel notes-toc-rail" aria-label="目录" data-testid="notes-toc">
      <h4 className="small muted">目录</h4>
      <ul>
        {items.map((h, i) => {
          const label = tocHeadingLabel(h.text);
          const id = slugs.slug(label);
          return (
            <li key={`${h.line}-${i}`} style={{ paddingLeft: Math.max(0, h.level - 1) * 10 }}>
              <button
                type="button"
                data-testid="notes-toc-item"
                title={label}
                onClick={() => onJump(h, id)}
              >
                {label}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
