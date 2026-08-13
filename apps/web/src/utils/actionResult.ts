/** Agent 写操作结果解析（与后端 __action__ 约定对齐） */

export interface ActionLink {
  label: string;
  href: string;
}

export interface ActionResultView {
  action: string;
  ok: boolean;
  summary: string;
  links: ActionLink[];
  resource?: Record<string, unknown>;
  /** 用于结果卡视觉变体 */
  kind: 'note' | 'category' | 'tags' | 'progress' | 'import' | 'repos' | 'session' | 'memory' | 'generic';
}

const ACTION_KIND: Record<string, ActionResultView['kind']> = {
  note_created: 'note',
  note_updated: 'note',
  category_ensured: 'category',
  category_applied: 'category',
  tags_ensured: 'tags',
  tags_applied: 'tags',
  progress_updated: 'progress',
  repos_imported: 'import',
  repos_selected: 'repos',
  memory_proposed: 'memory',
  session_projects: 'session',
};

export function isActionResult(value: unknown): value is Record<string, unknown> {
  return (
    !!value &&
    typeof value === 'object' &&
    !Array.isArray(value) &&
    typeof (value as Record<string, unknown>).__action__ === 'string'
  );
}

export function parseActionResult(value: unknown): ActionResultView | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const obj = value as Record<string, unknown>;

  // 兼容旧标记（无 __action__）
  if (obj.__session_projects__ && typeof obj.__action__ !== 'string') {
    const count = obj.count ?? (Array.isArray(obj.project_ids) ? obj.project_ids.length : 0);
    return {
      action: 'session_projects',
      ok: obj.ok !== false,
      summary: `会话已绑定 ${count} 个项目`,
      links: [{ label: '项目库', href: '/projects' }],
      resource:
        obj.project_ids && typeof obj === 'object'
          ? { type: 'session', project_ids: obj.project_ids, count }
          : undefined,
      kind: 'session',
    };
  }
  if (obj.__memory_proposal__ && typeof obj.__action__ !== 'string') {
    return {
      action: 'memory_proposed',
      ok: true,
      summary:
        typeof obj.message === 'string'
          ? obj.message
          : '记忆提案已排队，需在侧栏确认后写入',
      links: [],
      kind: 'memory',
    };
  }

  if (typeof obj.__action__ !== 'string') return null;
  const action = obj.__action__;
  const summary =
    typeof obj.summary === 'string' && obj.summary.trim()
      ? obj.summary.trim()
      : action;
  const linksRaw = Array.isArray(obj.links) ? obj.links : [];
  const links: ActionLink[] = linksRaw
    .filter((x): x is Record<string, unknown> => !!x && typeof x === 'object')
    .map((x) => ({
      label: String(x.label ?? '打开'),
      href: String(x.href ?? '#'),
    }))
    .filter((l) => l.href && l.href !== '#');

  const resource =
    obj.resource && typeof obj.resource === 'object' && !Array.isArray(obj.resource)
      ? (obj.resource as Record<string, unknown>)
      : undefined;

  return {
    action,
    ok: obj.ok !== false && !obj.error,
    summary,
    links,
    resource,
    kind: ACTION_KIND[action] ?? 'generic',
  };
}

/** 从工具结果中提取面向用户的一行摘要（供 RunTrace / 子 Agent） */
export function actionSummaryFromToolResult(result: unknown): string | null {
  const parsed = parseActionResult(result);
  if (parsed?.summary) return parsed.summary;
  if (result && typeof result === 'object' && !Array.isArray(result)) {
    const r = result as Record<string, unknown>;
    if (typeof r.error === 'string' && r.error) return r.error;
    if (r.__session_projects__) {
      return `会话上下文已更新（${r.count ?? 0} 个项目）`;
    }
    if (r.__memory_proposal__) {
      return typeof r.message === 'string' ? r.message : '已提交记忆提案';
    }
  }
  return null;
}

export function toolCallsHaveAction(toolCalls: Array<{ result?: unknown }> | undefined): boolean {
  return (toolCalls ?? []).some((tc) => parseActionResult(tc.result) != null);
}
