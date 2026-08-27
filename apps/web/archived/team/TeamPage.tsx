/** 团队页三栏:成员(内置人格 + 自建,分两组不混排)/ 详情 / 运行实例与权限矩阵。
 * skill 清单与全文查看在详情栏(选人格时并列展示 skills 区)。
 */

import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { Degraded } from '@/shell/Degraded';
import { INSTANCE_POLL_MS, useTeamStore } from './teamStore';
import { MemberDetail } from './MemberDetail';
import { SpawnForm } from './SpawnForm';
import { InstanceRow } from './InstanceRow';
import { PermissionMatrix } from './PermissionMatrix';

export function TeamPage() {
  const {
    loading, error, init, personas, definitions, running, skills, matrix,
    refreshInstances,
  } = useTeamStore();
  const [selected, setSelected] = useState<{ kind: 'persona' | 'custom'; key: string } | null>(null);
  const [creating, setCreating] = useState(false);
  const [skillOpen, setSkillOpen] = useState<string | null>(null);
  const [skillText, setSkillText] = useState('');
  const [now, setNow] = useState(Date.now() / 1000);

  useEffect(() => {
    void init();
  }, [init]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refreshInstances();
      setNow(Date.now() / 1000); // 耗时列每轮刷新
    }, INSTANCE_POLL_MS);
    return () => window.clearInterval(timer);
  }, [refreshInstances]);

  if (error) {    return (
      <Degraded
        code={error.code}
        message={`agent 数据不可用:${error.message}`}
        hint="其余页面不受影响"
        onRetry={() => void init()}
      />
    );
  }

  const persona = selected?.kind === 'persona'
    ? personas.find((p) => p.key === selected.key) ?? null
    : null;
  const definition = selected?.kind === 'custom'
    ? definitions.find((d) => d.name === selected.key) ?? null
    : null;

  const openSkill = async (name: string) => {
    if (skillOpen === name) {
      setSkillOpen(null);
      return;
    }
    setSkillOpen(name);
    setSkillText('加载中…');
    callCapability<{ text: string }>('agent', 'read_skill', { name })
      .then((doc) => setSkillText(doc.text))
      .catch(() => setSkillText('读取失败'));
  };

  return (
    <section className="team-page">
      {loading ? (
        <div className="loading-spinner">
          <div className="spinner" />
        </div>
      ) : null}
      <div className="team-layout">
        <aside className="team-list">
          <div className="label">内置人格</div>
          {personas.map((p) => (
            <button
              key={p.key}
              type="button"
              className={`team-member ${selected?.kind === 'persona' && selected.key === p.key ? 'active' : ''}`}
              onClick={() => {
                setSelected({ kind: 'persona', key: p.key });
                setCreating(false);
              }}
            >
              <span className="team-member__name">{p.display_name}</span>
              <span className="small muted">{p.key === 'lucien' ? '常驻' : p.default_mode}</span>
            </button>
          ))}
          <div className="label">自建 subagent</div>
          {definitions.length === 0 ? (
            <div className="small muted">还没有;点下方新建。</div>
          ) : null}
          {definitions.map((d) => (
            <button
              key={d.name}
              type="button"
              className={`team-member team-member--custom ${selected?.kind === 'custom' && selected.key === d.name ? 'active' : ''}`}
              onClick={() => {
                setSelected({ kind: 'custom', key: d.name });
                setCreating(false);
              }}
            >
              <span className="team-member__name mono">{d.name}</span>
              <span className="small muted">{d.mode}</span>
            </button>
          ))}
          <button
            type="button"
            className={`btn btn-sm ${creating ? 'btn-primary' : ''}`}
            onClick={() => setCreating((v) => !v)}
          >
            + 新建 subagent
          </button>
        </aside>

        <div className="team-main">
          {creating ? (
            <SpawnForm onDone={() => setCreating(false)} />
          ) : (
            <MemberDetail persona={persona} definition={definition} />
          )}

          <div className="matrix-spacer" />
          <div className="label">Skills</div>
          <div className="team-skills">
            {skills.map((s) => (
              <div key={s.name} className="team-skill">
                <button
                  type="button"
                  className="team-skill__head"
                  onClick={() => openSkill(s.name)}
                >
                  <span className="mono small">{s.name}</span>
                  <span className="small muted">{s.description}</span>
                </button>
                {skillOpen === s.name ? (
                  <pre className="team-detail__prompt mono">{skillText}</pre>
                ) : null}
              </div>
            ))}
          </div>
        </div>

        <aside className="team-side">
          <div className="node-editor__tabs">
            <span className="label">运行实例</span>
            <span className="small muted">不持久,重启清空</span>
          </div>
          {running.length === 0 ? (
            <div className="small muted">当前没有实例;发任务后这里出现。</div>
          ) : (
            running.map((i) => <InstanceRow key={i.id} inst={i} now={now} />)
          )}
          <div className="matrix-spacer" />
          <PermissionMatrix matrix={matrix} />
        </aside>
      </div>
    </section>
  );
}
