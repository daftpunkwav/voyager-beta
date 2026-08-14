/** 资源库:store SSE 状态机、导入 CONFLICT 语义、元数据编辑参数。 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ImportDialog } from '@/pages/sources/ImportDialog';
import { RepoDetail } from '@/pages/sources/RepoDetail';
import { type RepoSummary, useSourcesStore } from '@/pages/sources/sourcesStore';

const callMock = vi.fn();

vi.mock('@/bridge/client', () => ({
  callCapability: (...args: unknown[]) => callMock(...args),
  ServiceError: class extends Error {
    code = '';
    hint = '';
  },
}));

function repo(p: Partial<RepoSummary> = {}): RepoSummary {
  return {
    id: 'r1',
    owner: 'langchain-ai',
    name: 'langgraph',
    url: 'https://github.com/langchain-ai/langgraph',
    description: '建 agent 图',
    stars: 1000,
    language: 'Python',
    category: '',
    tags: [],
    progress: 'none',
    note: '',
    local_path: '',
    status: 'ready',
    error: '',
    source: 'github',
    added_ts: 1,
    updated_ts: 2,
    ...p,
  };
}

beforeEach(() => {
  callMock.mockReset();
  useSourcesStore.setState({
    repos: [],
    categories: [],
    sort: 'added',
    desc: true,
    category: '',
    loading: false,
    error: null,
    progress: {},
  });
});

describe('sourcesStore.dispatch 状态机', () => {
  it('task.progress 记录进度;source.ready 清进度并置 ready', () => {
    useSourcesStore.setState({ repos: [repo({ id: 's1', status: 'importing' })] });
    useSourcesStore.getState().dispatch({
      type: 'task.progress',
      payload: { source_id: 's1', progress: 0.4, stage: 'clone' },
    });
    expect(useSourcesStore.getState().progress.s1).toEqual({ progress: 0.4, stage: 'clone' });
    useSourcesStore.getState().dispatch({ type: 'source.ready', payload: { source_id: 's1' } });
    expect(useSourcesStore.getState().progress.s1).toBeUndefined();
    expect(useSourcesStore.getState().repos[0].status).toBe('ready');
  });

  it('task.failed 置 failed 并带 error', () => {
    useSourcesStore.setState({ repos: [repo({ id: 's1', status: 'importing' })] });
    useSourcesStore.getState().dispatch({
      type: 'task.failed',
      payload: { source_id: 's1', error: 'git clone 失败' },
    });
    const r = useSourcesStore.getState().repos[0];
    expect(r.status).toBe('failed');
    expect(r.error).toBe('git clone 失败');
  });

  it('source.removed 移除卡片', () => {
    useSourcesStore.setState({ repos: [repo({ id: 's1' })] });
    useSourcesStore.getState().dispatch({ type: 'source.removed', payload: { source_id: 's1' } });
    expect(useSourcesStore.getState().repos).toHaveLength(0);
  });
});

describe('importUrls CONFLICT 语义', () => {
  it('重复导入标记为已导入(ok),错误则 ok=false', async () => {
    callMock.mockImplementation((_d, name) => {
      if (name === 'list_repos') return Promise.resolve([]);
      if (name === 'list_categories') return Promise.resolve([]);
      if (name === 'import_repo') {
        return Promise.reject(
          Object.assign(new Error('仓库已导入'), { code: 'SOURCES.CONFLICT' }),
        );
      }
      return Promise.resolve({});
    });
    const outcomes = await useSourcesStore.getState().importUrls(
      ['https://github.com/a/b'],
      '',
    );
    expect(outcomes[0].ok).toBe(true);
    expect(outcomes[0].message).toContain('已导入');
  });
});

describe('ImportDialog 多行导入', () => {
  it('非法 URL 阻止提交;合法逐条导入', async () => {
    callMock.mockImplementation((_d, name) => {
      if (name === 'import_repo') return Promise.resolve({ job_id: 'j1' });
      return Promise.resolve([]);
    });
    render(<ImportDialog onDone={() => {}} />);
    const ta = screen.getByPlaceholderText(/每行一个/) as HTMLTextAreaElement;
    const btn = () => screen.getByRole('button', { name: /导入.*个/ }) as HTMLButtonElement;
    fireEvent.change(ta, {
      target: { value: 'https://github.com/a/b\nnotaurl\nhttps://github.com/c/d' },
    });
    expect(btn().disabled).toBe(true); // 非法行阻止
    expect(screen.getByText(/非法链接/)).toBeTruthy();

    fireEvent.change(ta, { target: { value: 'https://github.com/a/b\nhttps://github.com/c/d' } });
    expect(btn().disabled).toBe(false);
    fireEvent.click(btn());
    const importCalls = () => callMock.mock.calls.filter(([, n]) => n === 'import_repo');
    await waitFor(() => expect(importCalls()).toHaveLength(2)); // 逐条
    await waitFor(() => expect(screen.getAllByText(/已开始导入/)).toHaveLength(2));
  });
});

describe('RepoDetail 元数据编辑', () => {
  it('失焦提交 set_repo_meta(分类/标签/进度/备注)', async () => {
    callMock.mockResolvedValue({ readme: '# R' });
    useSourcesStore.setState({ repos: [repo()] });
    render(<RepoDetail repoId="r1" onClose={() => {}} />);

    const inputs = screen.getAllByRole('textbox');
    // 分类输入(第一个)与标签输入(第二个)
    fireEvent.change(inputs[0], { target: { value: 'Agent 框架' } });
    fireEvent.change(inputs[1], { target: { value: '编排, 状态机' } });
    fireEvent.blur(inputs[1]);
    await waitFor(() =>
      expect(callMock).toHaveBeenCalledWith('sources', 'set_repo_meta', {
        repo_id: 'r1',
        category: 'Agent 框架',
        tags: ['编排', '状态机'],
        progress: 'none',
        note: '',
      }),
    );
  });

  it('README 打开详情才拉取', async () => {
    callMock.mockResolvedValue({ readme: '# Hello' });
    useSourcesStore.setState({ repos: [repo()] });
    render(<RepoDetail repoId="r1" onClose={() => {}} />);
    await waitFor(() =>
      expect(callMock).toHaveBeenCalledWith('sources', 'get_readme', { repo_id: 'r1' }),
    );
  });
});
