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
  orchestrator: 'L',
  hub: 'L',
  lucien: 'L',
  recon: 'I',
  scout: 'I',
  navigator: 'I',
  iris: 'I',
  explainer: 'E',
  mentor: 'E',
  elio: 'E',
  organizer: 'M',
  curator: 'M',
  scribe: 'M',
  miyai: 'M',
  graph_guide: 'A',
  atlas: 'A',
};

export const AGENT_TAG_CLASS: Record<string, string> = {
  orchestrator: 'agent-tag-orchestrator',
  hub: 'agent-tag-orchestrator',
  lucien: 'agent-tag-orchestrator',
  recon: 'agent-tag-recon',
  scout: 'agent-tag-recon',
  navigator: 'agent-tag-recon',
  iris: 'agent-tag-recon',
  explainer: 'agent-tag-explainer',
  mentor: 'agent-tag-explainer',
  elio: 'agent-tag-explainer',
  organizer: 'agent-tag-organizer',
  curator: 'agent-tag-organizer',
  scribe: 'agent-tag-organizer',
  miyai: 'agent-tag-organizer',
  graph_guide: 'agent-tag-graph-guide',
  atlas: 'agent-tag-graph-guide',
};

export const AGENT_ROLE_LABELS: Record<string, string> = {
  orchestrator: '统筹者',
  hub: '统筹者',
  lucien: '统筹者',
  recon: '侦察检索',
  scout: '侦察检索',
  navigator: '侦察检索',
  iris: '侦察检索',
  explainer: '讲解导师',
  mentor: '讲解导师',
  elio: '讲解导师',
  organizer: '策展整理',
  curator: '策展整理',
  scribe: '策展整理',
  miyai: '策展整理',
  graph_guide: '图谱向导',
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
