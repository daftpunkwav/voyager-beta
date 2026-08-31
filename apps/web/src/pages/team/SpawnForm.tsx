/** 造人表单:注册自建 subagent,含同名覆盖确认。
 *
 *  自己加载 list_personas(下拉)/list_tools(白名单)/list_subagents(同名检查),
 *  造人成功后触发 defsEvents 通知 DefinitionGrid 刷新。
 */

import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { GlassCard } from '@/components/common/GlassCard';
import { GlassSelect } from '@/components/common/GlassSelect';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { extractErrorMessage } from '@/utils/errors';
import { notifyTeamDefsChanged } from './defsEvents';
import { patchTeamSnapshot } from './provider';
import { NAME_RE, MODE_OPTIONS, NETWORK_OPTIONS } from './constants';
import { SpawnToolFields } from './SpawnToolFields';
import type { PersonaItem, SubagentDef, ToolItem } from './types';

export function SpawnForm() {
  const [personas, setPersonas] = useState<PersonaItem[]>([]);
  const [tools, setTools] = useState<ToolItem[]>([]);
  const [definitions, setDefinitions] = useState<SubagentDef[]>([]);
  const [dataLoading, setDataLoading] = useState(true);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [mode, setMode] = useState('react');
  const [persona, setPersona] = useState('');
  const [toolMode, setToolMode] = useState<'all' | 'custom'>('all');
  const [pickedTools, setPickedTools] = useState<string[]>([]);
  const [maxRounds, setMaxRounds] = useState('');
  const [maxToolRounds, setMaxToolRounds] = useState('');
  const [networkMode, setNetworkMode] = useState('');

  const [confirmOverwrite, setConfirmOverwrite] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');

  const addToast = useUIStore((s) => s.addToast);

  useEffect(() => {
    let alive = true;
    (async () => {
      setDataLoading(true);
      try {
        const [p, t, s] = await Promise.all([
          callCapability<PersonaItem[] | { personas: PersonaItem[] }>('agent', 'list_personas', {}),
          callCapability<ToolItem[] | { tools: ToolItem[] }>('agent', 'list_tools', {}),
          callCapability<{ definitions?: SubagentDef[] }>('agent', 'list_subagents', {}),
        ]);
        if (!alive) return;
        const personasArr = Array.isArray(p) ? p : p.personas ?? [];
        const toolsArr = Array.isArray(t) ? t : t.tools ?? [];
        const defsArr = s.definitions ?? [];
        setPersonas(personasArr);
        setTools(toolsArr);
        setDefinitions(defsArr);
      } catch (err) {
        if (alive) addToast({ type: 'error', message: `造人表单数据加载失败:${extractErrorMessage(err)}` });
      } finally {
        if (alive) setDataLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [addToast]);

  const toggleTool = (toolName: string) => {
    setPickedTools((prev) =>
      prev.includes(toolName) ? prev.filter((n) => n !== toolName) : [...prev, toolName],
    );
  };

  const parseRounds = (draft: string): number | null => {
    const trimmed = draft.trim();
    if (trimmed === '') return null;
    const n = Number(trimmed);
    if (!Number.isInteger(n) || n < 1) return NaN;
    return n;
  };

  const resetForm = () => {
    setName('');
    setDescription('');
    setMode('react');
    setPersona('');
    setToolMode('all');
    setPickedTools([]);
    setMaxRounds('');
    setMaxToolRounds('');
    setNetworkMode('');
  };

  const doRegister = async () => {
    setBusy(true);
    setFormError('');
    try {
      const args: Record<string, unknown> = {
        name: name.trim(),
        description: description.trim(),
        mode,
        persona,
      };
      if (toolMode === 'custom') args.allowed_tools = pickedTools;
      if (maxRounds.trim() !== '') args.max_rounds = Number(maxRounds);
      if (maxToolRounds.trim() !== '') args.max_tool_calls = Number(maxToolRounds);
      if (networkMode) args.network_mode = networkMode;
      await callCapability('agent', 'register_subagent', args);
      addToast({ type: 'success', message: `已注册自建 subagent:${name.trim()}` });

      const s = await callCapability<{ definitions?: SubagentDef[] }>('agent', 'list_subagents', {});
      const defsArr = s.definitions ?? [];
      setDefinitions(defsArr);
      patchTeamSnapshot({ definitions: defsArr.length });
      notifyTeamDefsChanged();
      resetForm();
    } catch (err) {
      addToast({ type: 'error', message: `注册失败:${extractErrorMessage(err)}` });
    } finally {
      setBusy(false);
    }
  };

  const submit = () => {
    const trimmedName = name.trim();
    if (!NAME_RE.test(trimmedName)) {
      setFormError('名称须为小写 snake_case(字母开头,只含小写字母、数字、下划线)');
      return;
    }
    if (!description.trim()) {
      setFormError('描述必填');
      return;
    }
    if (toolMode === 'custom' && pickedTools.length === 0) {
      setFormError('指定白名单时至少勾选 1 项工具');
      return;
    }
    if (Number.isNaN(parseRounds(maxRounds))) {
      setFormError('ReAct 轮数须为正整数,留空跟随全局');
      return;
    }
    if (Number.isNaN(parseRounds(maxToolRounds))) {
      setFormError('工具轮数须为正整数,留空跟随全局');
      return;
    }
    setFormError('');
    if (definitions.some((d) => d.name === trimmedName)) {
      setConfirmOverwrite(true);
      return;
    }
    void doRegister();
  };

  if (dataLoading) {
    return (
      <section className="team-section">
        <h2 className="h3">造人 · 注册自建 subagent</h2>
        <LoadingSpinner label="加载造人表单中…" />
      </section>
    );
  }

  return (
    <>
      <section className="team-section">
        <h2 className="h3">造人 · 注册自建 subagent</h2>
        <GlassCard>
          <form
            className="spawn-form"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <div className="field-group">
              <label className="field-label" htmlFor="spawn-name">名称</label>
              <input
                id="spawn-name"
                className="field input"
                value={name}
                placeholder="repo_scout"
                onChange={(e) => setName(e.target.value)}
              />
              <span className="field-help">小写 snake_case,如 repo_scout</span>
            </div>
            <div className="field-group">
              <label className="field-label" htmlFor="spawn-desc">描述</label>
              <input
                id="spawn-desc"
                className="field input"
                value={description}
                placeholder="这个 subagent 负责什么"
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
            <div className="spawn-form__row">
              <div className="field-group">
                <span className="field-label">执行模式</span>
                <GlassSelect
                  aria-label="执行模式"
                  value={mode}
                  options={MODE_OPTIONS}
                  onChange={setMode}
                />
              </div>
              <div className="field-group">
                <span className="field-label">人格预设</span>
                <GlassSelect
                  aria-label="人格预设"
                  value={persona}
                  options={[
                    { value: '', label: '不绑定' },
                    ...personas.map((p) => ({ value: p.key, label: p.display_name })),
                  ]}
                  onChange={setPersona}
                />
              </div>
            </div>
            <div className="spawn-form__row">
              <div className="field-group">
                <label className="field-label" htmlFor="spawn-rounds">ReAct 轮数</label>
                <input
                  id="spawn-rounds"
                  className="field input"
                  type="number"
                  min={1}
                  placeholder="跟随全局"
                  value={maxRounds}
                  onChange={(e) => setMaxRounds(e.target.value)}
                />
                <span className="field-help">留空跟随全局;派出时只能比全局更严</span>
              </div>
              <div className="field-group">
                <label className="field-label" htmlFor="spawn-tool-rounds">工具轮数</label>
                <input
                  id="spawn-tool-rounds"
                  className="field input"
                  type="number"
                  min={1}
                  placeholder="跟随全局"
                  value={maxToolRounds}
                  onChange={(e) => setMaxToolRounds(e.target.value)}
                />
              </div>
            </div>
            <div className="field-group">
              <span className="field-label">网络权限</span>
              <GlassSelect
                aria-label="网络权限档位"
                value={networkMode}
                options={NETWORK_OPTIONS}
                onChange={setNetworkMode}
              />
              <span className="field-help">比全局松的档位派出时会被夹回全局档位</span>
            </div>
            <SpawnToolFields
              toolMode={toolMode}
              onToolMode={setToolMode}
              tools={tools}
              pickedTools={pickedTools}
              onToggleTool={toggleTool}
            />
            {formError && <p className="field-error">{formError}</p>}
            <div>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={submit}>
                注册
              </button>
            </div>
          </form>
        </GlassCard>
      </section>

      <ConfirmDialog
        open={confirmOverwrite}
        title="覆盖已存在的 subagent?"
        message={`「${name.trim()}」已注册,继续将覆盖原定义。`}
        confirmLabel="覆盖"
        danger
        onConfirm={() => {
          setConfirmOverwrite(false);
          void doRegister();
        }}
        onCancel={() => setConfirmOverwrite(false)}
      />
    </>
  );
}
