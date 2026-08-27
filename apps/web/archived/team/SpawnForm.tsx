/** 自建 subagent 表单:name/mode/description/工具白名单(勾选 = 白名单裁剪,
 * 不勾任何 = 不裁剪;坑 1:语义是 Toolbelt.trimmed,不是提示词约束)。
 */

import { useState } from 'react';
import { MODES, useTeamStore } from './teamStore';

export function SpawnForm({ onDone }: { onDone: () => void }) {
  const { tools, register } = useTeamStore();
  const personas = useTeamStore((s) => s.personas);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [mode, setMode] = useState('react');
  const [persona, setPersona] = useState('');
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const toggle = (t: string) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  };

  const valid = /^[a-z][a-z0-9_]*$/.test(name.trim()) && description.trim().length > 0;

  const submit = async () => {
    setBusy(true);
    setMessage('');
    try {
      await register({
        name: name.trim(),
        description: description.trim(),
        mode,
        // 勾选项即白名单;一个不勾 = null(不裁剪)
        allowed_tools: checked.size > 0 ? [...checked].sort() : null,
        persona: persona || '',
      });
      setMessage(`已注册「${name.trim()}」;在对话中让 Lucien 按名派遣它。`);
      setName('');
      setDescription('');
      setChecked(new Set());
    } catch (err) {
      setMessage((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="team-detail spawn-form">
      <div className="node-editor__tabs">
        <span className="label">新建 subagent</span>
        <span className="sources-toolbar__spacer" />
        <button type="button" className="btn btn-sm" onClick={onDone}>
          关闭
        </button>
      </div>
      <input
        className="setting-input mono"
        value={name}
        placeholder="名称(小写 snake_case,如 scout)"
        onChange={(e) => setName(e.target.value)}
      />
      <input
        className="setting-input"
        value={description}
        placeholder="职责描述(派遣时作为任务约束注入)"
        onChange={(e) => setDescription(e.target.value)}
      />
      <label className="small muted">
        执行模式
        <select className="setting-input" value={mode} onChange={(e) => setMode(e.target.value)}>
          {MODES.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </label>
      <label className="small muted">
        挂靠人格(可空)
        <select className="setting-input" value={persona} onChange={(e) => setPersona(e.target.value)}>
          <option value="">(无)</option>
          {personas.filter((p) => p.key !== 'lucien').map((p) => (
            <option key={p.key} value={p.key}>{p.display_name}</option>
          ))}
        </select>
      </label>
      <div className="label">
        工具白名单(勾选 {checked.size} 项;不勾 = 不裁剪)
      </div>
      <div className="spawn-form__tools">
        {tools.map((t) => (
          <label key={t.name} className="spawn-form__tool" title={t.description}>
            <input
              type="checkbox"
              checked={checked.has(t.name)}
              onChange={() => toggle(t.name)}
            />
            <span className="mono small">{t.name}</span>
          </label>
        ))}
      </div>
      {message ? <div className="small node-editor__msg">{message}</div> : null}
      <button
        type="button"
        className="btn btn-primary"
        disabled={busy || !valid}
        onClick={() => void submit()}
      >
        {busy ? '注册中…' : '注册'}
      </button>
    </div>
  );
}
