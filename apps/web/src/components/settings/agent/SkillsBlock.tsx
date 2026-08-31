import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import type { SkillItem } from './types';

/** 技能清单(只读):索引常驻对话上下文,这里仅展示 */
export function SkillsBlock() {
  const [skills, setSkills] = useState<SkillItem[] | null>(null);
  const [skillsLoadFailed, setSkillsLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<SkillItem[]>('agent', 'list_skills', {})
      .then((items) => {
        if (alive) setSkills(Array.isArray(items) ? items : []);
      })
      .catch(() => {
        if (alive) setSkillsLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">技能</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        可复用的过程包。索引（名称 + 一句描述）常驻对话上下文；需要步骤时 Agent 用 load_skill 取全文。
      </p>
      {skillsLoadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>读取失败请刷新。</p>
      ) : skills === null ? (
        <p className="muted" style={{ fontSize: 12 }}>技能清单加载中…</p>
      ) : skills.length === 0 ? (
        <p className="muted" style={{ fontSize: 12 }}>
          还没有技能。把 SKILL.md 放到工作目录的 skills/&lt;名称&gt;/ 下，重启开发服务后生效。
        </p>
      ) : (
        <ul className="memory-entry-list">
          {skills.map((s) => (
            <li key={s.name} className="memory-entry">
              <span className="memory-kind">{s.name}</span>
              <span className="memory-entry-summary">{s.description}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
