/** 团队 — Agent 与 subagent 管理(基于 agent.list_subagents / list_personas / list_tools)。
 *
 * 列出:人格预设 / 自建 subagent 定义(register_subagent 造人,§9.4.4)/
 * 工具面名册 / subagent 实例(spawner.instances 全量,按 status 渲染)。
 * 运行中实例可急停(cancel_run);后端无 runtime 生命周期 SSE,实例列表
 * 挂载期每 5s 轮询(与 Chat 徽章同口径,单次失败静默等下轮)。
 */

import { useEffect, useState } from 'react';
import { callCapability, ServiceError } from '@/bridge/client';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { GlassCard } from '@/components/common/GlassCard';
import { GlassSelect } from '@/components/common/GlassSelect';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { extractErrorMessage } from '@/utils/errors';

/** 名称规则与后端 SubagentDef 同一道正则(agent/subagent/registry.py),前端先拦一道 */
const NAME_RE = /^[a-z][a-z0-9_]*$/;

/** 执行模式七值(agent/subagent/modes.py);提交值仍是后端枚举 */
const MODE_OPTIONS = [
  { value: 'react', label: 'ReAct' },
  { value: 'plan_execute', label: '计划执行' },
  { value: 'cot', label: '思维链' },
  { value: 'tot', label: '思维树' },
  { value: 'got', label: '思维图' },
  { value: 'reflexion', label: '反思' },
  { value: 'direct', label: '直答' },
];
const MODE_LABELS: Record<string, string> = Object.fromEntries(
  MODE_OPTIONS.map((o) => [o.value, o.label]),
);

interface RunningSubagent {
  id: string;
  name: string;
  status: string;
  goal: string;
  started_ts: number;
}

/** list_subagents.definitions 条目;allowed_tools 为 null 表示不裁剪(全部工具) */
interface SubagentDef {
  name: string;
  mode: string;
  description: string;
  persona: string;
  allowed_tools: string[] | null;
}

interface PersonaItem {
  key: string;
  display_name: string;
  style: string;
  default_mode: string;
  tool_allow: string[] | null;
  system_prompt: string;
}

interface ToolItem {
  name: string;
  description: string;
}

/** started_ts 是秒级 unix 时间戳(agent/runtime/state.py time.time()) */
function relativeTime(ts: number): string {
  if (!ts) return '';
  const diff = Math.max(0, Date.now() / 1000 - ts);
  if (diff < 60) return '刚刚';
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  return `${Math.floor(diff / 86400)} 天前`;
}

/** 实例状态 → 状态色片(shell.css .inst--*) */
function statusChipClass(status: string): string {
  switch (status) {
    case 'running':
      return 'inst--running';
    case 'completed':
      return 'inst--done';
    case 'failed':
      return 'inst--failed';
    case 'paused':
      return 'inst--paused';
    default:
      return 'inst--muted';
  }
}

export function TeamPage() {
  const [personas, setPersonas] = useState<PersonaItem[]>([]);
  const [tools, setTools] = useState<ToolItem[]>([]);
  const [definitions, setDefinitions] = useState<SubagentDef[]>([]);
  const [instances, setInstances] = useState<RunningSubagent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryTick, setRetryTick] = useState(0);

  // 造人表单:persona 为 '' 表示不绑定;toolMode 显式二选一,避免「空列表=全部」的隐含语义
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [mode, setMode] = useState('react');
  const [persona, setPersona] = useState('');
  const [toolMode, setToolMode] = useState<'all' | 'custom'>('all');
  const [pickedTools, setPickedTools] = useState<string[]>([]);
  const [confirmOverwrite, setConfirmOverwrite] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');

  const addToast = useUIStore((s) => s.addToast);

  // 初次加载:人格 / 工具 / 定义 / 实例
  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [p, t, s] = await Promise.all([
          callCapability<PersonaItem[] | { personas: PersonaItem[] }>('agent', 'list_personas', {}),
          callCapability<ToolItem[] | { tools: ToolItem[] }>('agent', 'list_tools', {}),
          callCapability<{ definitions?: SubagentDef[]; running?: RunningSubagent[] }>(
            'agent',
            'list_subagents',
            {},
          ),
        ]);
        if (!alive) return;
        setPersonas(Array.isArray(p) ? p : p.personas ?? []);
        setTools(Array.isArray(t) ? t : t.tools ?? []);
        setDefinitions(s.definitions ?? []);
        setInstances(s.running ?? []);
      } catch (err) {
        if (alive) setError(extractErrorMessage(err));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [retryTick]);

  // 实例轮询:初载完成后每 5s 拉一次;非关键路径,单次失败静默等下轮
  useEffect(() => {
    if (loading) return;
    let alive = true;
    const timer = setInterval(() => {
      callCapability<{ running?: RunningSubagent[] }>('agent', 'list_subagents', {})
        .then((s) => {
          if (alive) setInstances(s.running ?? []);
        })
        .catch(() => {});
    }, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [loading]);

  const toggleTool = (toolName: string) => {
    setPickedTools((prev) =>
      prev.includes(toolName) ? prev.filter((n) => n !== toolName) : [...prev, toolName],
    );
  };

  /** 提交注册。不裁剪时不传 allowed_tools(后端空列表是 falsy 会被并进 None,前端不制造这种形态) */
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
      await callCapability('agent', 'register_subagent', args);
      addToast({ type: 'success', message: `已注册自建 subagent:${name.trim()}` });
      const s = await callCapability<{ definitions?: SubagentDef[] }>('agent', 'list_subagents', {});
      setDefinitions(s.definitions ?? []);
      setName('');
      setDescription('');
      setMode('react');
      setPersona('');
      setToolMode('all');
      setPickedTools([]);
    } catch (err) {
      // INVALID_INPUT(名称/模式不合法)的后端 message 直接给用户,不静默
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
    setFormError('');
    // 同名覆盖写盘没有确认,前端补一道
    if (definitions.some((d) => d.name === trimmedName)) {
      setConfirmOverwrite(true);
      return;
    }
    void doRegister();
  };

  /** 急停一个实例。停 chat(对话主实例)时同步清对话思考态,与 Chat 急停按钮同语义;
   *  团队页用 toast 反馈,不往对话流塞系统消息 */
  const stopRun = async (r: RunningSubagent) => {
    const isChat = r.id === 'chat' || r.name === 'chat';
    try {
      await callCapability('agent', 'cancel_run', { id_or_name: r.id });
      if (isChat) useChatStore.setState({ thinking: false });
      addToast({
        type: 'success',
        message: isChat ? '已中断对话主实例。' : `已中断 ${r.name}。`,
      });
      setInstances((prev) => prev.filter((x) => x.id !== r.id && x.name !== r.id));
    } catch (err) {
      // NOT_FOUND = 目标本就没在跑(轮询间隙里结束了):从列表拿掉即可
      const notFound = err instanceof ServiceError && err.code.includes('NOT_FOUND');
      if (notFound) {
        setInstances((prev) => prev.filter((x) => x.id !== r.id && x.name !== r.id));
      }
      addToast({
        type: 'error',
        message: notFound ? `${r.name} 已不在运行。` : `急停失败:${extractErrorMessage(err)}`,
      });
    }
  };

  const personaName = (key: string) => {
    if (!key) return '不绑定';
    return personas.find((p) => p.key === key)?.display_name ?? key;
  };

  if (loading) {
    return (
      <div className="team-page page-scaffold">
        <LoadingSpinner label="加载团队信息中…" />
      </div>
    );
  }
  if (error) {
    return (
      <div className="team-page page-scaffold">
        <div className="page-scaffold__state">
          <EmptyState
            title="加载失败"
            description={error}
            icon={EmptyStateIcons.team}
            onRetry={() => setRetryTick((n) => n + 1)}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="team-page page-scaffold">
      <div className="page-scaffold__body">

      <section className="team-section">
        <h2 className="h3">人格</h2>
        <div className="team-grid">
          {personas.length === 0 ? (
            <EmptyState title="暂无人格" description="后端未注册任何 Agent 人格" icon={EmptyStateIcons.team} />
          ) : (
            personas.map((p) => (
              <GlassCard key={p.key} className="persona-card">
                <div className="persona-card__head">
                  <h3 className="h3">{p.display_name}</h3>
                  <span className="chip brand">{p.key}</span>
                </div>
                <p className="muted small">{p.style}</p>
                <p className="small">默认模式:{p.default_mode}</p>
                <p className="small">
                  工具面:
                  {p.tool_allow
                    ? `${p.tool_allow.length} 项`
                    : '不裁剪(全部工具)'}
                </p>
                <details className="small">
                  <summary>系统提示词</summary>
                  <pre className="system-prompt">{p.system_prompt}</pre>
                </details>
              </GlassCard>
            ))
          )}
        </div>
      </section>

      <section className="team-section">
        <h2 className="h3">自建 subagent</h2>
        <div className="team-grid">
          {definitions.length === 0 ? (
            <EmptyState
              title="还没有自建 subagent"
              description="用下方「造人」表单注册一个;注册后落盘持久,刷新页面仍在"
              icon={EmptyStateIcons.team}
            />
          ) : (
            definitions.map((d) => (
              <GlassCard key={d.name} className="persona-card">
                <div className="persona-card__head">
                  <h3 className="h3">{d.name}</h3>
                  <span className="chip brand">{MODE_LABELS[d.mode] ?? d.mode}</span>
                </div>
                <p className="muted small">{d.description}</p>
                <p className="small">人格:{personaName(d.persona)}</p>
                <p className="small">
                  工具面:
                  {d.allowed_tools
                    ? `${d.allowed_tools.length} 项`
                    : '不裁剪(全部工具)'}
                </p>
                {d.allowed_tools && d.allowed_tools.length > 0 && (
                  <details className="small">
                    <summary>工具清单</summary>
                    <pre className="system-prompt">{d.allowed_tools.join('\n')}</pre>
                  </details>
                )}
              </GlassCard>
            ))
          )}
        </div>
      </section>

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
            <div className="field-group">
              <span className="field-label">能力面</span>
              <label className="spawn-form__tool">
                <input
                  type="radio"
                  name="spawn-tool-mode"
                  checked={toolMode === 'all'}
                  onChange={() => setToolMode('all')}
                />
                不裁剪(全部工具)
              </label>
              <label className="spawn-form__tool">
                <input
                  type="radio"
                  name="spawn-tool-mode"
                  checked={toolMode === 'custom'}
                  onChange={() => setToolMode('custom')}
                />
                指定白名单
              </label>
              {toolMode === 'custom' && (
                <div className="spawn-form__tools">
                  {tools.map((t) => (
                    <label key={t.name} className="spawn-form__tool" title={t.description}>
                      <input
                        type="checkbox"
                        checked={pickedTools.includes(t.name)}
                        onChange={() => toggleTool(t.name)}
                      />
                      <code className="mono">{t.name}</code>
                    </label>
                  ))}
                </div>
              )}
              <span className="field-help">
                白名单是真裁剪:没勾的工具该 subagent 真的调不了(write_file / run_shell 等含其中)。
              </span>
            </div>
            {formError && <p className="field-error">{formError}</p>}
            <div>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={submit}>
                注册
              </button>
            </div>
          </form>
        </GlassCard>
      </section>

      <section className="team-section">
        <h2 className="h3">工具面名册</h2>
        <GlassCard>
          {tools.length === 0 ? (
            <EmptyState title="暂未加载" description="agent 进程尚未启动或未注册工具" icon={EmptyStateIcons.team} />
          ) : (
            <ul className="tool-list">
              {tools.map((t) => (
                <li key={t.name} className="tool-list__item">
                  <code className="mono">{t.name}</code>
                  <span className="muted small">{t.description}</span>
                </li>
              ))}
            </ul>
          )}
        </GlassCard>
      </section>

      <section className="team-section">
        <h2 className="h3">subagent 实例</h2>
        <GlassCard>
          {instances.length === 0 ? (
            <EmptyState
              title="暂无实例"
              description="subagent 派生后出现在这里;对话主实例 chat 在对话进行时存在"
              icon={EmptyStateIcons.team}
            />
          ) : (
            <ul className="inst-list">
              {instances.map((r) => (
                <li key={r.id} className="inst-row">
                  <div className="inst-row__head">
                    <span className="inst-row__name">{r.name}</span>
                    <span className={`inst-row__status ${statusChipClass(r.status)}`}>{r.status}</span>
                    {r.status === 'running' && (
                      <button
                        type="button"
                        className="btn btn-sm btn-danger"
                        title={r.name === 'chat' ? '急停将中断当前对话' : `急停 ${r.name}`}
                        onClick={() => void stopRun(r)}
                      >
                        急停
                      </button>
                    )}
                  </div>
                  <span className="inst-row__goal">{r.goal}</span>
                  <span className="muted small">
                    {r.id} · {relativeTime(r.started_ts)}
                    {r.name === 'chat' || r.id === 'chat'
                      ? ' · 对话主实例,急停会中断当前对话'
                      : ''}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </GlassCard>
      </section>
    </div>

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
    </div>
  );
}

export default TeamPage;
