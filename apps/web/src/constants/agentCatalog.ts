/**
 * Agent 目录 — 单一数据源，新增 Agent 只需在此追加一条记录。
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
    id: 'hub',
    name: 'Hub',
    tagline: '对话管家',
    intro: '统筹多 Agent 协作，管理上下文与任务分发，是你的总入口。',
    color: 'linear-gradient(135deg,#4a3aff,#9d4edd)',
  },
  {
    id: 'scout',
    name: 'Scout',
    tagline: '快速分析',
    intro: '快速扫描仓库结构，给出项目全貌与上手建议。',
    color: 'linear-gradient(135deg,#ff9f0a,#ff6f00)',
  },
  {
    id: 'mentor',
    name: 'Mentor',
    tagline: '深度讲解',
    intro: '深入讲解源码与设计，按掌握程度定制讲解深度。',
    color: 'linear-gradient(135deg,#9d4edd,#c879ff)',
  },
  {
    id: 'navigator',
    name: 'Navigator',
    tagline: '学习规划',
    intro: '拆解学习目标，推荐下一步该看的项目与笔记。',
    color: 'linear-gradient(135deg,#00b8d4,#00d4aa)',
  },
  {
    id: 'curator',
    name: 'Curator',
    tagline: '分类管家',
    intro: '自动分类打标签，整理混乱的 Star 与导入列表。',
    color: 'linear-gradient(135deg,#34c759,#30d158)',
  },
  {
    id: 'scribe',
    name: 'Scribe',
    tagline: '笔记助手',
    intro: '生成结构化笔记，自动关联到项目与技术栈。',
    color: 'linear-gradient(135deg,#ff375f,#ff6b8a)',
  },
  {
    id: 'atlas',
    name: 'Atlas',
    tagline: '图谱向导',
    intro: '解读知识图谱中的项目关联，建议探索与迁移学习路径。',
    color: 'linear-gradient(135deg,#5ac8fa,#007aff)',
  },
];
