/** 团队页:权限矩阵从设置键渲染、SpawnForm 提交参数(白名单语义)、实例状态。 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PermissionMatrix } from '@/pages/team/PermissionMatrix';
import { SpawnForm } from '@/pages/team/SpawnForm';
import { formatElapsed } from '@/pages/team/InstanceRow';
import { useTeamStore } from '@/pages/team/teamStore';

const callMock = vi.fn();

vi.mock('@/bridge/client', () => ({
  callCapability: (...args: unknown[]) => callMock(...args),
  ServiceError: class extends Error {
    code = '';
    hint = '';
  },
}));

const MATRIX = {
  networkMode: 'whitelist',
  networkDomains: ['github.com', 'arxiv.org'],
  workspaceDir: 'workspace',
  roundsMax: 20,
  roundsToolMax: 40,
  maxConcurrent: 3,
};

beforeEach(() => {
  callMock.mockReset();
  useTeamStore.setState({
    personas: [
      { key: 'lucien', display_name: 'Lucien', style: '热心', default_mode: 'react',
        tool_allow: null, system_prompt: '统筹' },
      { key: 'iris', display_name: 'Iris', style: '敏锐', default_mode: 'react',
        tool_allow: ['web_search'], system_prompt: '侦察' },
    ],
    definitions: [],
    running: [],
    skills: [],
    tools: [
      { name: 'read_file', description: '读文件' },
      { name: 'write_file', description: '写文件' },
      { name: 'web_search', description: '搜索' },
    ],
    matrix: null,
    loading: false,
    error: null,
  });
});

describe('PermissionMatrix 只读渲染', () => {
  it('四维从设置键渲染;白名单域名列出;单元格跳设置页 agent 组', () => {
    render(<MemoryRouter><PermissionMatrix matrix={MATRIX} /></MemoryRouter>);
    expect(screen.getByText('域名白名单')).toBeTruthy();
    expect(screen.getByText(/github\.com、arxiv\.org/)).toBeTruthy();
    expect(screen.getByText(/工作目录 workspace/)).toBeTruthy();
    expect(screen.getByText('20 轮 / 40 次工具')).toBeTruthy();
    expect(screen.getByText(/secret 项仅用户可写/)).toBeTruthy();
    const links = screen.getAllByRole('link');
    expect(links.every((a) => a.getAttribute('href') === '/settings?module=agent')).toBe(true);
  });

  it('网络关闭模式显示拒答文案', () => {
    render(
      <MemoryRouter>
        <PermissionMatrix matrix={{ ...MATRIX, networkMode: 'off' }} />
      </MemoryRouter>,
    );
    expect(screen.getByText('关闭(不出网)')).toBeTruthy();
    expect(screen.getByText('一切出网请求被拒')).toBeTruthy();
  });

  it('null 矩阵显示加载中', () => {
    render(<PermissionMatrix matrix={null} />);
    expect(screen.getByText(/加载中/)).toBeTruthy();
  });
});

describe('SpawnForm 提交参数', () => {
  it('勾选工具 -> allowed_tools 数组;不勾 -> null(不裁剪)', async () => {
    callMock.mockResolvedValue({});
    render(<SpawnForm onDone={() => {}} />);
    fireEvent.change(screen.getByPlaceholderText(/snake_case/), {
      target: { value: 'scout' },
    });
    fireEvent.change(screen.getByPlaceholderText(/职责描述/), {
      target: { value: '只读侦察员' },
    });
    fireEvent.click(screen.getByRole('button', { name: /注册/ }));
    // 未勾任何工具:null
    await waitFor(() =>
      expect(callMock).toHaveBeenCalledWith('agent', 'register_subagent', {
        name: 'scout', description: '只读侦察员', mode: 'react',
        allowed_tools: null, persona: '',
      }),
    );

    // 勾两个工具再提交(第一次提交后表单已清空,重填全部字段)
    callMock.mockClear();
    fireEvent.change(screen.getByPlaceholderText(/snake_case/), {
      target: { value: 'scout2' },
    });
    fireEvent.change(screen.getByPlaceholderText(/职责描述/), {
      target: { value: '只读侦察员' },
    });
    for (const title of ['搜索', '读文件']) {
      const input = screen.getByTitle(title).querySelector('input');
      expect(input).toBeTruthy();
      fireEvent.click(input as HTMLInputElement);
    }
    fireEvent.click(screen.getByRole('button', { name: /注册/ }));
    await waitFor(() =>
      expect(callMock).toHaveBeenCalledWith('agent', 'register_subagent', {
        name: 'scout2', description: '只读侦察员', mode: 'react',
        allowed_tools: ['read_file', 'web_search'], persona: '',
      }),
    );
  });

  it('非法名称(大写)阻止提交', () => {
    render(<SpawnForm onDone={() => {}} />);
    fireEvent.change(screen.getByPlaceholderText(/snake_case/), {
      target: { value: 'Scout' },
    });
    fireEvent.change(screen.getByPlaceholderText(/职责描述/), {
      target: { value: 'x' },
    });
    expect((screen.getByRole('button', { name: /注册/ }) as HTMLButtonElement).disabled)
      .toBe(true);
  });
});

describe('实例耗时格式', () => {
  it('秒/分/时三档;无时间戳显示 —', () => {
    const now = 10_000;
    expect(formatElapsed(0, now)).toBe('—');
    expect(formatElapsed(now - 42, now)).toBe('42s');
    expect(formatElapsed(now - 125, now)).toBe('2m5s');
  });
});
