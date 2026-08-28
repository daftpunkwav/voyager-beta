/**
 * Agent 目录 — 单一数据源。id 为职责结构 ID;name 为显示名。
 */
export interface AgentDefinition {
  id: string;
  name: string;
  /** 短标签（卡片左侧） */
  tagline: string;
  /** 简介（卡片右侧，0.618:1 布局中的长文案区） */
  intro: string;
  color: string;
}

/** 视口内完整展示的 Agent 数量 */
export const AGENT_CAROUSEL_VISIBLE = 4;

/** 自动轮播间隔（毫秒）— 偏慢，便于阅读 */
export const AGENT_CAROUSEL_INTERVAL_MS = 5_000;

/** 滑动过渡时长（毫秒） */
export const AGENT_CAROUSEL_TRANSITION_MS = 900;

export const AGENT_CATALOG: AgentDefinition[] = [
  {
    id: 'orchestrator',
    name: 'Lucien',
    tagline: '统筹者',
    intro: '统筹多 Agent 协作，管理上下文与任务分发，是你的总入口。',
    color: 'linear-gradient(135deg,#4a3aff,#9d4edd)',
  },
  {
    id: 'recon',
    name: 'Iris',
    tagline: '侦察检索',
    intro: '快速扫描仓库结构，给出项目全貌与上手建议。',
    color: 'linear-gradient(135deg,#ff9f0a,#ff6f00)',
  },
  {
    id: 'explainer',
    name: 'Elio',
    tagline: '讲解导师',
    intro: '深入讲解源码与设计，按掌握程度定制讲解深度。',
    color: 'linear-gradient(135deg,#9d4edd,#c879ff)',
  },
  {
    id: 'organizer',
    name: 'Miyai',
    tagline: '策展整理',
    intro: '分类打标签、写笔记、整理入库，保持知识库整洁。',
    color: 'linear-gradient(135deg,#34c759,#30d158)',
  },
  {
    id: 'graph_guide',
    name: 'Atlas',
    tagline: '图谱向导',
    intro: '解读知识图谱中的项目关联，建议探索与迁移学习路径。',
    color: 'linear-gradient(135deg,#5ac8fa,#007aff)',
  },
];
