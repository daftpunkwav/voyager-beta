import { Link } from 'react-router-dom';
import {
  parseActionResult,
  type ActionResultView,
} from '@/utils/actionResult';

interface ActionResultCardProps {
  result: unknown;
  /** 工具名，仅作兜底标题 */
  toolName?: string;
}

function detailLine(view: ActionResultView): string | null {
  const r = view.resource;
  if (!r) return null;
  if (view.kind === 'note') {
    const title = typeof r.title === 'string' ? r.title : '';
    const project = typeof r.project_name === 'string' ? r.project_name : '';
    if (title && project) return `${title} · ${project}`;
    return title || null;
  }
  if (view.kind === 'tags' && Array.isArray(r.tags)) {
    const names = r.tags
      .map((t) =>
        t && typeof t === 'object' && 'name' in t
          ? String((t as { name: unknown }).name)
          : ''
      )
      .filter(Boolean);
    return names.length ? names.join(' · ') : null;
  }
  if (view.kind === 'progress' && typeof r.progress === 'string') {
    return `进度 → ${r.progress}`;
  }
  if (view.kind === 'import') {
    const ok = r.succeeded;
    const fail = r.failed;
    if (ok !== undefined || fail !== undefined) {
      return `成功 ${ok ?? 0} · 失败 ${fail ?? 0}`;
    }
  }
  if (view.kind === 'category' && typeof r.category_name === 'string') {
    return r.category_name;
  }
  return null;
}

/** 面向用户的动作结果卡（写库成功后的确认与跳转） */
export function ActionResultCard({ result, toolName }: ActionResultCardProps) {
  const view = parseActionResult(result);
  if (!view) return null;
  const detail = detailLine(view);

  return (
    <div
      className={`action-result action-result--${view.kind}${view.ok ? '' : ' is-error'}`}
      data-testid="action-result"
      data-action={view.action}
    >
      <div className="action-result__head">
        <span className="action-result__badge" aria-hidden>
          {view.ok ? 'OK' : '!'}
        </span>
        <div className="action-result__text">
          <p className="action-result__summary">{view.summary}</p>
          {detail && <p className="action-result__detail">{detail}</p>}
          {!view.summary && toolName && (
            <p className="action-result__detail">{toolName}</p>
          )}
        </div>
      </div>
      {view.links.length > 0 && (
        <div className="action-result__links">
          {view.links.map((link) => (
            <Link key={`${link.href}_${link.label}`} className="action-result__link" to={link.href}>
              {link.label}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
