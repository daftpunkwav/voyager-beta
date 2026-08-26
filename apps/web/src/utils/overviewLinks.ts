import type { ActivityItem } from '@/api/types';

/** 最近活动条目跳转路径（按 type 区分） */
export function activityItemHref(item: ActivityItem): string {
  switch (item.type) {
    case 'import':
    case 'progress':
      return item.project_id ? `/projects/${item.project_id}` : '/projects';
    case 'note':
      return item.project_id ? `/projects/${item.project_id}` : '/notes';
    case 'agent':
    default:
      return '/agent';
  }
}
