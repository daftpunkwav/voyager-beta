/** 设置页技能清单单测(phase-11):list_skills 渲染 name+description、
 *  空态提示、失败只本块提示不整页崩;不调 getApi()。 */

import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock, getApiMock } = vi.hoisted(() => ({
  callCapabilityMock: vi.fn(),
  getApiMock: vi.fn(),
}));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

vi.mock('@/api/client', () => ({ getApi: getApiMock }));

import { AgentSettingsSection } from '@/components/settings/AgentSettingsSection';
import type { Settings } from '@/api/types';
import { useUIStore } from '@/stores/uiStore';

const SNAPSHOT = {
  profile: { summary: '', items: [] },
  episodic: { recent: [], shown: 0 },
  semantic: { recent: [], shown: 0 },
  working: { size: 0 },
  retention_days: 90,
  purged_episodic: 0,
};

/** 按 key 返回的设置库(与 agentSettingsLimits 同法,避免类型不对连带别的块失败) */
const SETTINGS: Record<string, unknown> = {
  'agent.style': '热心',
  'agent.memory.retention_days': 90,
  'agent.rounds.max': 20,
  'agent.rounds.tool_max': 40,
  'agent.network.mode': 'whitelist',
  'agent.network.domains': ['github.com'],
  'agent.workspace.dir': 'workspace',
};

function backend(skills: unknown, failSkills = false) {
  return (_domain: string, name: string, args: Record<string, unknown>) => {
    switch (name) {
      case 'list_skills':
        return failSkills ? Promise.reject(new Error('boom')) : Promise.resolve(skills);
      case 'get_memory':
        return Promise.resolve(SNAPSHOT);
      case 'get_setting':
        return Promise.resolve({ value: SETTINGS[String(args.key)] });
      default:
        return Promise.resolve({});
    }
  };
}

const noop = () => Promise.resolve();

function renderSection(impl: ReturnType<typeof backend>) {
  callCapabilityMock.mockImplementation(impl);
  render(
    <AgentSettingsSection
      settings={{ agent_code_of_conduct: '', agent_guidelines: [] } as Settings}
      updateSettings={noop}
    />,
  );
}

beforeEach(() => {
  callCapabilityMock.mockReset();
  getApiMock.mockReset();
  useUIStore.setState({ toasts: [] });
});

describe('设置页技能清单(phase-11)', () => {
  it('挂载经 agent.list_skills 拉取并渲染 name + description', async () => {
    renderSection(
      backend([{ name: 'explore-repo', description: '了解一个仓库的流程' }]),
    );
    await waitFor(() => expect(screen.getByText('explore-repo')).toBeTruthy());
    expect(screen.getByText('了解一个仓库的流程')).toBeTruthy();
    expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'list_skills', {});
    expect(getApiMock).not.toHaveBeenCalled();
  });

  it('空清单显示放置指引', async () => {
    renderSection(backend([]));
    await waitFor(() =>
      expect(screen.getByText(/skills\/<名称>\//)).toBeTruthy(),
    );
  });

  it('加载失败只本块提示「读取失败请刷新」,其余区块照常', async () => {
    renderSection(backend([], true));
    await waitFor(() => expect(screen.getByText('读取失败请刷新。')).toBeTruthy());
    // 同页其他区块不整页崩:工作目录输入照常渲染
    expect((screen.getByLabelText('工作目录') as HTMLInputElement).value).toBe('workspace');
  });
});
