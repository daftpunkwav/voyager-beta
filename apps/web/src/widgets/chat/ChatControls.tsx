/** 对话控制面(§10.2):仲裁模式指示与切换、急停、运行中 subagent 徽章。
 *
 * Chat 主页与常驻悬浮窗共用本组件与同一 chatStore(§10.12)。
 * 后端无 runtime 生命周期 SSE,徽章走 5s 轮询 agent.list_subagents(只渲染
 * status=running 的实例;该能力返回的是全量实例,completed/cancelled 等靠
 * status 字段过滤)。急停按钮固定停对话主实例('chat');点徽章停对应 id。
 */

import { useCallback, useEffect, useState } from 'react';
import { callCapability, ServiceError } from '@/bridge/client';
import { useChatStore } from '@/stores/chatStore';
import { GlassSelect } from '@/components/common/GlassSelect';
import { extractErrorMessage } from '@/utils/errors';

const ARBITER_KEY = 'agent.arbiter.mode';

/** 用户可见文案;提交值仍是后端枚举 queue|auto|guide(§9.7) */
const ARBITER_OPTIONS = [
  { value: 'queue', label: '仲裁:排队' },
  { value: 'auto', label: '仲裁:自动' },
  { value: 'guide', label: '仲裁:引导' },
];

/** list_subagents.running 条目(status 为 RunStatus.value,见 agent/runtime/state.py) */
interface RunningInstance {
  id: string;
  name: string;
  status: string;
  goal: string;
  started_ts: number;
}

export function ChatControls() {
  const thinking = useChatStore((s) => s.thinking);
  const [arbiter, setArbiter] = useState<string | null>(null); // null = 未加载
  const [arbiterBusy, setArbiterBusy] = useState(false);
  const [running, setRunning] = useState<RunningInstance[]>([]);
  const [stopping, setStopping] = useState(false);

  // 仲裁模式读取(与设置页风格控件同一 settings.get_setting 通道)
  useEffect(() => {
    let alive = true;
    callCapability<{ value?: string; default?: string }>('settings', 'get_setting', {
      key: ARBITER_KEY,
    })
      .then((item) => {
        if (alive) setArbiter(item.value ?? item.default ?? 'queue');
      })
      .catch(() => {
        if (alive) setArbiter(''); // 读取失败:下拉置灰显示「读取失败」,不猜一个值
      });
    return () => {
      alive = false;
    };
  }, []);

  // 运行中徽章:挂载期间每 5s 轮询;徽章非关键路径,单次失败静默等下轮
  useEffect(() => {
    let alive = true;
    const pull = () => {
      callCapability<{ running?: RunningInstance[] }>('agent', 'list_subagents', {})
        .then((s) => {
          if (alive) setRunning((s.running ?? []).filter((r) => r.status === 'running'));
        })
        .catch(() => {});
    };
    pull();
    const timer = setInterval(pull, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  const stop = useCallback(async (idOrName: string) => {
    const stopChat = idOrName === 'chat';
    setStopping(true);
    try {
      await callCapability<{ cancelled: string[] }>('agent', 'cancel_run', { id_or_name: idOrName });
      // 只有停对话主实例才清思考态;停后台徽章不得假装主对话已结束
      if (stopChat) useChatStore.setState({ thinking: false });
      useChatStore
        .getState()
        .addSystem(stopChat ? '已中断当前对话任务。' : `已发送中断请求(${idOrName})。`);
      setRunning((prev) => prev.filter((r) => r.id !== idOrName && r.name !== idOrName));
    } catch (err) {
      // NOT_FOUND = 目标本就没在跑(常见于 thinking 状态残留)
      const notFound = err instanceof ServiceError && err.code.includes('NOT_FOUND');
      if (stopChat) useChatStore.setState({ thinking: false });
      useChatStore.getState().addSystem(
        notFound ? '没有正在运行的实例。' : `急停失败:${extractErrorMessage(err)}`,
      );
      if (notFound) {
        setRunning((prev) => prev.filter((r) => r.id !== idOrName && r.name !== idOrName));
      }
    } finally {
      setStopping(false);
    }
  }, []);

  const changeArbiter = (value: string) => {
    if (arbiterBusy) return; // 进行中忽略连点,避免先发的回读覆盖后发的选择
    const prev = arbiter;
    setArbiter(value); // 乐观更新,失败回滚
    setArbiterBusy(true);
    callCapability('settings', 'set_setting', { key: ARBITER_KEY, value })
      // set 成功后经 get_setting 回读,确认持久化的就是所选值
      .then(() =>
        callCapability<{ value?: string }>('settings', 'get_setting', { key: ARBITER_KEY }),
      )
      .then((item) => setArbiter(item.value ?? value))
      .catch((err) => {
        setArbiter(prev);
        useChatStore.getState().addSystem(`仲裁模式切换失败:${extractErrorMessage(err)}`);
      })
      .finally(() => setArbiterBusy(false));
  };

  // 急停按钮只停 chat;后台实例要点对应徽章。有 running 不意味着对话在跑。
  const canStop = thinking;

  return (
    <div className="chat-controls">
      <GlassSelect
        size="sm"
        value={arbiter ?? ''}
        aria-label="仲裁模式"
        disabled={arbiter === null || arbiter === '' || arbiterBusy}
        options={
          arbiter === null
            ? [{ value: '', label: '仲裁:读取中…' }]
            : arbiter === ''
              ? [{ value: '', label: '仲裁:读取失败' }]
              : ARBITER_OPTIONS
        }
        onChange={changeArbiter}
      />
      <button
        type="button"
        className="btn btn-sm chat-controls__stop"
        disabled={!canStop || stopping}
        title="中断当前对话任务"
        onClick={() => void stop('chat')}
      >
        急停
      </button>
      {running.length > 0 ? (
        <div className="chat-controls__badges" aria-label="运行中的 subagent">
          {running.map((r) => (
            <button
              key={r.id}
              type="button"
              className="chat-badge"
              title={`${r.goal}\n状态:${r.status}\n点击中断该实例`}
              aria-label={`${r.name} · ${r.status}`}
              disabled={stopping}
              onClick={() => void stop(r.id)}
            >
              {r.name}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
