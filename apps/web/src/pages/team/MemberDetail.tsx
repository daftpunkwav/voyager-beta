/** 成员详情:内置人格(风格/默认模式/工具面/系统提示,只读)或
 * 自建 subagent 定义(模式/白名单/描述)。工具名直译展示(坑 1:白名单语义)。
 */

import type { Persona, SubagentDef } from './teamStore';

export function MemberDetail({
  persona,
  definition,
}: {
  persona: Persona | null;
  definition: SubagentDef | null;
}) {
  if (!persona && !definition) {
    return <div className="muted small team-detail__empty">选择左侧成员查看详情。</div>;
  }

  if (persona) {
    return (
      <div className="team-detail">
        <div className="team-detail__head">
          <span className="team-detail__name">{persona.display_name}</span>
          <span className="tag-chip">{persona.default_mode}</span>
          <span className="setting-badge setting-badge--none">{persona.style}</span>
        </div>
        <div className="label">工具面{persona.tool_allow === null ? '(不裁剪)' : `(${persona.tool_allow.length} 项白名单)`}</div>
        {persona.tool_allow === null ? (
          <div className="small muted">全部工具(统筹者不裁剪)</div>
        ) : (
          <div className="team-detail__tools">
            {persona.tool_allow.map((t) => (
              <span key={t} className="tag-chip mono">{t}</span>
            ))}
          </div>
        )}
        <div className="label">系统提示(只读)</div>
        <pre className="team-detail__prompt mono">{persona.system_prompt}</pre>
      </div>
    );
  }

  const d = definition as SubagentDef;
  return (
    <div className="team-detail">
      <div className="team-detail__head">
        <span className="team-detail__name mono">{d.name}</span>
        <span className="tag-chip">{d.mode}</span>
        {d.persona ? <span className="setting-badge setting-badge--none">人格 {d.persona}</span> : null}
      </div>
      <div className="small">{d.description}</div>
      <div className="label">工具面{d.allowed_tools === null ? '(不裁剪)' : `(${d.allowed_tools.length} 项白名单)`}</div>
      {d.allowed_tools === null ? (
        <div className="small muted">全部工具</div>
      ) : (
        <div className="team-detail__tools">
          {d.allowed_tools.map((t) => (
            <span key={t} className="tag-chip mono">{t}</span>
          ))}
        </div>
      )}
    </div>
  );
}
