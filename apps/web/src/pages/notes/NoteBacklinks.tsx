/** 反链:引用了当前笔记的笔记;点击跳转。 */

import { Link } from 'react-router-dom';
import { useBacklinks } from '@/hooks/useNotes';
import { routes } from '@/utils/routes';

export function BacklinkPanel({ noteId }: { noteId: string }) {
  const { data } = useBacklinks(noteId);
  const backlinks = data?.backlinks ?? [];
  if (backlinks.length === 0) return null;
  return (
    <div className="backlink-panel">
      <h4 className="small muted">反链({backlinks.length})</h4>
      <ul>
        {backlinks.map((b) => (
          <li key={b.id}>
            <Link to={routes.note(b.id)}>{b.title}</Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
