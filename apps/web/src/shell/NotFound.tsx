import { Link } from 'react-router-dom';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { routes } from '@/utils/routes';

/** 未知路由:不再静默落到总览,避免用户以为跳转成功。 */
export function NotFound() {
  return (
    <div className="page-scaffold">
      <div className="page-scaffold__state">
        <EmptyState
          title="没有这个页面"
          description="链接可能已过期,或地址写错了。"
          icon={EmptyStateIcons.inbox}
          action={
            <Link to={routes.overview} className="btn btn-primary">
              回到总览
            </Link>
          }
        />
      </div>
    </div>
  );
}
