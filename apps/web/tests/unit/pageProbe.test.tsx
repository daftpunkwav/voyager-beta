/** 页面感知:probe 摘要形态、activity 节流/去抖/开关、PageProbe 路由上报。 */

import { act, render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  initActivityReport,
  reportPageView,
  reportPointer,
  reportSelection,
  setActivityReportEnabled,
} from '@/bridge/activity';
import { PageProbe } from '@/widgets/PageProbe';
import { PAGE_PROBES } from '@/widgets/probes';
import { useGraphStore } from '@/pages/graph/graphStore';
import { useNotesStore } from '@/pages/notes/notesStore';

const callMock = vi.fn();
const fetchMock = vi.fn();

vi.mock('@/bridge/client', () => ({
  callCapability: (...args: unknown[]) => callMock(...args),
  ServiceError: class extends Error {
    code = '';
    hint = '';
  },
}));
vi.mock('@/bridge/stream', () => ({ subscribe: () => () => {} }));

beforeEach(() => {
  vi.useFakeTimers();
  callMock.mockReset();
  fetchMock.mockReset().mockResolvedValue({ ok: true });
  vi.stubGlobal('fetch', fetchMock);
  setActivityReportEnabled(true);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('activity 节流与开关', () => {
  it('pointer 1s 节流:窗口内只发一次', async () => {
    reportPointer('notes', 'note-1');
    reportPointer('notes', 'note-2');
    reportPointer('notes', 'note-3');
    await vi.advanceTimersByTimeAsync(10);
    const calls = fetchMock.mock.calls.filter(([u]) => String(u).includes('/api/activity'));
    expect(calls).toHaveLength(1);
  });

  it('selection 500ms 去抖 + 同文本不重发', async () => {
    reportSelection('notes', 'a'.repeat(300));
    reportSelection('notes', 'b'); // 覆盖前一个未发
    await vi.advanceTimersByTimeAsync(600);
    const calls = fetchMock.mock.calls.filter(([u]) => String(u).includes('/api/activity'));
    expect(calls).toHaveLength(1);
    expect((calls[0][1] as RequestInit).body).toContain('"text":"b"'); // 截断后一条

    reportSelection('notes', 'b'); // 同文本
    await vi.advanceTimersByTimeAsync(600);
    expect(fetchMock.mock.calls.filter(([u]) => String(u).includes('/api/activity'))).toHaveLength(1);
  });

  it('隐私开关关闭:page_view 与 pointer 零请求', async () => {
    setActivityReportEnabled(false);
    reportPageView('/notes');
    reportPointer('/notes', 'x');
    reportSelection('/notes', 'y');
    await vi.advanceTimersByTimeAsync(600);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('initActivityReport 读设置;读失败按默认开', async () => {
    callMock.mockResolvedValueOnce({ value: false });
    await initActivityReport();
    reportPageView('/notes');
    expect(fetchMock).not.toHaveBeenCalled();

    callMock.mockRejectedValueOnce(new Error('down'));
    await initActivityReport();
    reportPageView('/notes');
    expect(fetchMock.mock.calls.filter(([u]) => String(u).includes('/api/activity'))).toHaveLength(1);
  });
});

describe('probe 摘要(索引级,不塞正文)', () => {
  it('notes:计数 + 当前打开标题;空数据(loading)返回 null', () => {
    useNotesStore.setState({
      loading: true, summaries: [], current: null,
    });
    expect(PAGE_PROBES['/notes'].report()).toBeNull();

    useNotesStore.setState({
      loading: false,
      summaries: [{ id: '1', title: 'A', tags: [], source_id: '', node_id: '',
                    created_ts: 1, updated_ts: 1, excerpt: '' }],
      current: { id: '1', title: 'ReAct 笔记', content: '', tags: [], source_id: '',
                 node_id: '', created_ts: 1, updated_ts: 1, excerpt: '' },
    });
    const out = PAGE_PROBES['/notes'].report();
    expect(out?.summary).toBe('1 篇笔记,当前打开《ReAct 笔记》');
    expect(out?.counts).toEqual({ notes: 1 });
    expect(out?.selected).toBe('ReAct 笔记');
  });

  it('graph:节点数与选中节点名', () => {
    const nodes = new Map();
    nodes.set('n1', { id: 'n1', label: 'Function', name: 'run',
                      qualified_name: 't.run', attrs: {}, source: 'code', actor: '' });
    useGraphStore.setState({
      project: 'toy', nodes, edges: new Map(), selected: 'n1',
      stats: { total_nodes: 9, total_edges: 4 }, loading: false,
    });
    const out = PAGE_PROBES['/graph'].report();
    expect(out?.summary).toContain('toy');
    expect(out?.summary).toContain('9 节点');
    expect(out?.selected).toBe('run');
  });
});

describe('PageProbe 路由上报', () => {
  it('路由变化发 page_view + 延迟页摘要;未注册页面只发 page_view', async () => {
    useNotesStore.setState({ loading: false, summaries: [], current: null });
    callMock.mockResolvedValue({});
    render(
      <MemoryRouter initialEntries={['/notes']}>
        <PageProbe />
      </MemoryRouter>,
    );
    await vi.advanceTimersByTimeAsync(900);
    const pageViews = fetchMock.mock.calls.filter(
      ([u, init]) => String(u).includes('/api/activity')
        && String((init as RequestInit).body).includes('page_view'),
    );
    expect(pageViews).toHaveLength(1);
    expect(pageViews[0][1]?.body).toContain('/notes');
    const summaries = callMock.mock.calls.filter(
      ([, name]) => name === 'report_page_context',
    );
    expect(summaries).toHaveLength(1);
    expect(summaries[0][2]).toMatchObject({ page: 'notes', summary: '0 篇笔记' });
  });

  it('开关关闭时 PageProbe 零请求', async () => {
    setActivityReportEnabled(false);
    render(
      <MemoryRouter initialEntries={['/notes']}>
        <PageProbe />
      </MemoryRouter>,
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(35_000);
    });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(callMock).not.toHaveBeenCalledWith('agent', 'report_page_context', expect.anything());
  });
});
