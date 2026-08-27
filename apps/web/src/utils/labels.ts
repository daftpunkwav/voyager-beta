import type { Category, ProjectProgress } from '@/api/types';
import { AGENT_CATALOG } from '@/constants/agentCatalog';

export type { AgentDefinition } from '@/constants/agentCatalog';
export { AGENT_CATALOG } from '@/constants/agentCatalog';

/** 与原型 app-shell.js PROGRESS_MAP 对齐 */
export const PROGRESS_LABELS: Record<ProjectProgress, string> = {
  none: '待开始',
  learning: '学习中',
  learned: '已学习',
  mastered: '已掌握',
};

export function progressLabel(p: ProjectProgress | string | undefined): string {
  if (!p) return '-';
  return PROGRESS_LABELS[p as ProjectProgress] ?? p;
}

/** Mock 兼容 id；真实环境以 API categories 为准 */
const CATEGORY_MAP: Record<string, string> = {
  cat_frontend: '前端',
  cat_backend: '后端',
  cat_ai: 'AI/ML',
  cat_data: 'AI/ML',
  cat_devops: 'DevOps',
  cat_mobile: '其他',
  cat_desktop: '其他',
  cat_game: '其他',
  cat_security: '其他',
  cat_tools: '其他',
  cat_learning: '其他',
  cat_other: '其他',
};

/** 按分类 id 解析显示名；优先使用 API 返回的 categories 列表 */
export function categoryLabel(
  id: string | undefined | null,
  categories?: Category[] | null,
): string {
  if (!id) return '-';
  if (categories?.length) {
    const hit = categories.find((c) => c.id === id);
    if (hit) return hit.name;
  }
  return CATEGORY_MAP[id] ?? id;
}

/** 根据分类名/id 选择 CSS 主题类 */
export function categoryCssClass(
  id: string | undefined | null,
  categories?: Category[] | null,
): string {
  if (!id) return 'cat-other';
  if (CATEGORY_MAP[id]) {
    const key = id.replace('cat_', '');
    return `cat-${key === 'data' ? 'ai' : key}`;
  }
  const name = (categories?.find((c) => c.id === id)?.name || '').toLowerCase();
  if (name.includes('前端') || name.includes('front')) return 'cat-frontend';
  if (name.includes('后端') || name.includes('back')) return 'cat-backend';
  if (name.includes('ai') || name.includes('ml') || name.includes('数据')) return 'cat-ai';
  if (name.includes('devops') || name.includes('运维')) return 'cat-devops';
  if (name.includes('移动') || name.includes('mobile')) return 'cat-mobile';
  if (name.includes('工具')) return 'cat-tools';
  return 'cat-other';
}

export const AGENT_INITIALS: Record<string, string> = {
  hub: 'H',
  scout: 'S',
  mentor: 'M',
  navigator: 'N',
  curator: 'C',
  scribe: 'S',
  atlas: 'A',
};

export const AGENT_TAG_CLASS: Record<string, string> = {
  hub: 'agent-tag-hub',
  scout: 'agent-tag-scout',
  mentor: 'agent-tag-mentor',
  navigator: 'agent-tag-navigator',
  curator: 'agent-tag-curator',
  scribe: 'agent-tag-scribe',
  atlas: 'agent-tag-navigator',
};

export const AGENT_ROLE_LABELS: Record<string, string> = {
  hub: '对话管家',
  scout: '快速分析',
  mentor: '深度讲解',
  navigator: '学习规划',
  curator: '分类管家',
  scribe: '笔记助手',
  atlas: '图谱向导',
};

/** @deprecated 请优先使用 AGENT_CATALOG；保留兼容字段 desc */
export const AGENT_CARDS = AGENT_CATALOG.map((a) => ({
  id: a.id,
  name: a.name,
  desc: a.tagline,
  intro: a.intro,
  color: a.color,
}));
