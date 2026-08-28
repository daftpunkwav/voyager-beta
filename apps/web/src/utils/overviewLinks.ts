import type { ActivityItem } from '@/api/types';
import { routes } from '@/utils/routes';

/** 最近活动条目跳转路径（按 type 区分） */
export function activityItemHref(item: ActivityItem): string {
  switch (item.type) {
    case 'import':
    case 'progress':
      return item.project_id ? routes.sourceRepo(item.project_id) : routes.sources;
    case 'note':
      return item.project_id ? routes.sourceRepo(item.project_id) : routes.notes;
    case 'agent':
    default:
      return routes.chat;
  }
}
