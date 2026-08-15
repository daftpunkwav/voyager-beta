/** IndexPanel:enqueue 202 -> 列表出现排队;cancel 传参;引擎徽标文案。 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { EngineBadge, IndexPanel } from '@/pages/graph/IndexPanel';
import { useGraphStore } from '@/pages/graph/graphStore';

const callMock = vi.fn();

vi.mock('@/bridge/client', () => ({
  callCapability: (...args: unknown[]) => callMock(...args),
  ServiceError: class extends Error {
    code = '';
    hint = '';
  },
}));

beforeEach(() => {
  callMock.mockReset();
  useGraphStore.setState({
    project: 'toy',
    projects: ['toy'],
    repos: [],
    engine: null,
  });
});

describe('IndexPanel enqueue/cancel', () => {
  it('手填项目名 -> enqueue 202 -> 列表出现排队;取消传 job_id', async () => {
    const job = {
      id: 'j1', project: 'demo', repo_path: 'workspace/repo/demo', priority: 100,
      status: 'queued' as const, attempts: 0, error: '', created_ts: 1, updated_ts: 2,
    };
    callMock.mockImplementation((_d: string, name: string) => {
      if (name === 'enqueue_index') return Promise.resolve({ job_id: 'j1' });
      if (name === 'list_index_jobs') return Promise.resolve([job]);
      if (name === 'list_repos') return Promise.resolve([]);
      return Promise.resolve({});
    });
    render(<IndexPanel onClose={() => {}} progress={{}} />);

    const input = screen.getByPlaceholderText(/手动建图路径/) as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'demo' } });
    fireEvent.click(screen.getByRole('button', { name: '入队索引' }));

    await waitFor(() =>
      expect(callMock).toHaveBeenCalledWith('graph', 'enqueue_index', {
        project: 'demo',
        repo_path: 'workspace/repo/demo',
      }),
    );
    await waitFor(() => expect(screen.getByText('排队')).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    await waitFor(() =>
      expect(callMock).toHaveBeenCalledWith('graph', 'cancel_index', { job_id: 'j1' }),
    );
  });

  it('资源库仓库选中 -> 项目名取 owner__name', async () => {
    callMock.mockImplementation((_d: string, name: string) => {
      if (name === 'enqueue_index') return Promise.resolve({ job_id: 'j2' });
      if (name === 'list_index_jobs') return Promise.resolve([]);
      if (name === 'list_repos') {
        return Promise.resolve([
          { owner: 'langchain-ai', name: 'langgraph', local_path: 'ws/langchain-ai__langgraph', status: 'ready' },
        ]);
      }
      return Promise.resolve({});
    });
    render(<IndexPanel onClose={() => {}} progress={{}} />);
    await waitFor(() =>
      expect(callMock).toHaveBeenCalledWith('sources', 'list_repos', {}),
    );

    fireEvent.change(screen.getByDisplayValue('-- 资源库仓库 --'), {
      target: { value: '0' },
    });
    fireEvent.click(screen.getByRole('button', { name: '入队索引' }));
    await waitFor(() =>
      expect(callMock).toHaveBeenCalledWith('graph', 'enqueue_index', {
        project: 'langchain-ai__langgraph',
        repo_path: 'ws/langchain-ai__langgraph',
      }),
    );
  });
});

describe('EngineBadge 诚实显示', () => {
  it('无数据不渲染;c 引擎;python 回退不标红', () => {
    const { container, rerender } = render(<EngineBadge />);
    expect(container.querySelector('.setting-badge')).toBeNull();

    useGraphStore.setState({ engine: { engine: 'c', healthy: true, fallback: false } });
    rerender(<EngineBadge />);
    expect(screen.getByText('C 引擎')).toBeTruthy();

    useGraphStore.setState({ engine: { engine: 'python', healthy: true, fallback: true } });
    rerender(<EngineBadge />);
    const badge = screen.getByText('Python 引擎(回退)');
    expect(badge.className).not.toContain('repo-badge--failed');
    expect(badge.className).not.toContain('degraded');
  });
});
