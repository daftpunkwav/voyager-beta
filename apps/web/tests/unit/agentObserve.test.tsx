/** 观察提示单测(phase-12 §9.2):agent.observe 渲染观察句、只留最新一条、
 *  agent.message 不清掉;设置页「自动建索引」开关打到 agent.observe.auto_index。 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import { AgentSettingsSection } from '@/components/settings/AgentSettingsSection';
import { ObserveLine } from '@/widgets/chat/MessageList';
import type { Settings } from '@/api/types';
import { useChatStore, type ChatEvent } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';

let seq = 0;
function dispatch(type: string, payload: Record<string, unknown>) {
  seq += 1;
  useChatStore.getState().dispatch({ seq, type, payload } as ChatEvent);
}

/** AgentSettingsSection 同页还会读记忆/技能/MCP,统一给空快照 */
const SNAPSHOT = {
  profile: { summary: '', items: [] },
  episodic: { recent: [], shown: 0 },
  semantic: { recent: [], shown: 0 },
  working: { size: 0 },
  retention_days: 90,
  purged_episodic: 0,
};

/** 按 key 分支的设置库;set_setting 写回,用例间重置 */
const SETTINGS: Record<string, unknown> = {
  'agent.style': '热心',
  'agent.memory.retention_days': 90,
  'agent.rounds.max': 20,
  'agent.rounds.tool_max': 40,
  'agent.network.mode': 'whitelist',
  'agent.network.domains': ['github.com'],
  'agent.workspace.dir': 'workspace',
  'agent.observe.auto_index': false,
};

function backend(_domain: string, name: string, args: Record<string, unknown>) {
  switch (name) {
    case 'get_memory':
      return Promise.resolve(SNAPSHOT);
    case 'get_setting':
      return Promise.resolve({ value: SETTINGS[String(args.key)] });
    case 'set_setting':
      SETTINGS[String(args.key)] = args.value;
      return Promise.resolve({ value: args.value });
    case 'list_skills':
    case 'list_mcp_servers':
      return Promise.resolve([]);
    default:
      return Promise.resolve({});
  }
}

beforeEach(() => {
  seq = 0;
  useChatStore.setState({
    messages: [],
    question: null,
    thinking: false,
    connected: true,
    currentStep: null,
    observe: null,
  });
  Object.assign(SETTINGS, { 'agent.observe.auto_index': false });
  callCapabilityMock.mockReset();
  callCapabilityMock.mockImplementation(backend);
  useUIStore.setState({ toasts: [] });
});

describe('ObserveLine(phase-12)', () => {
  it('dispatch agent.observe 渲染观察句;默认不显示已行动', () => {
    dispatch('agent.observe', {
      content: '用户导入了 langgraph 且已解析完成。可考虑为其建立图谱索引。',
      acted: false,
    });
    render(<ObserveLine />);
    expect(screen.getByRole('status')).toHaveTextContent('langgraph');
    expect(screen.queryByText(/已派出自动索引/)).toBeNull();
  });

  it('acted=true 附加「已派出自动索引」', () => {
    dispatch('agent.observe', { content: '可考虑建立图谱索引。', acted: true });
    render(<ObserveLine />);
    expect(screen.getByRole('status')).toHaveTextContent('已派出自动索引');
  });

  it('只留最新一条:新的覆盖旧的', () => {
    dispatch('agent.observe', { content: '第一条观察 alpha', acted: false });
    dispatch('agent.observe', { content: '第二条观察 beta', acted: false });
    render(<ObserveLine />);
    expect(screen.getByRole('status')).toHaveTextContent('beta');
    expect(screen.queryByText(/alpha/)).toBeNull();
  });

  it('agent.message 到达不清掉观察条(发完话仍想看见)', () => {
    dispatch('agent.observe', { content: '可考虑建立图谱索引。', acted: false });
    dispatch('agent.message', { content: '回复正文' });
    render(<ObserveLine />);
    expect(screen.getByRole('status')).toHaveTextContent('可考虑建立图谱索引');
  });
});

describe('设置:自动建索引开关(phase-12)', () => {
  it('勾选打到 agent.observe.auto_index(true)', async () => {
    render(
      <AgentSettingsSection
        settings={{ agent_code_of_conduct: '', agent_guidelines: [] } as Settings}
        updateSettings={() => Promise.resolve()}
      />,
    );
    const box = (await screen.findByLabelText(
      '导入完成后自动建图谱索引',
    )) as HTMLInputElement;
    expect(box.checked).toBe(false); // 默认关:只提示不自动建索引
    fireEvent.click(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.observe.auto_index',
        value: true,
      }),
    );
  });

  it('取消勾选保存 false;保存成功出 toast', async () => {
    Object.assign(SETTINGS, { 'agent.observe.auto_index': true });
    render(
      <AgentSettingsSection
        settings={{ agent_code_of_conduct: '', agent_guidelines: [] } as Settings}
        updateSettings={() => Promise.resolve()}
      />,
    );
    const box = (await screen.findByLabelText(
      '导入完成后自动建图谱索引',
    )) as HTMLInputElement;
    expect(box.checked).toBe(true);
    fireEvent.click(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.observe.auto_index',
        value: false,
      }),
    );
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'success')).toBe(true),
    );
  });
});
