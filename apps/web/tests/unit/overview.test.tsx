/** 总览卡:每卡独立拉数,正常态关键数字、错误态复用 Degraded(独立降级)。 */

import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UsageCard } from '@/pages/overview/cards/UsageCard';
import { TasksCard } from '@/pages/overview/cards/TasksCard';
import { SourcesCard } from '@/pages/overview/cards/SourcesCard';
import { NotesCard } from '@/pages/overview/cards/NotesCard';
import { ActivityCard } from '@/pages/overview/cards/ActivityCard';

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
vi.mock('@/bridge/events', () => ({ EventType: { SERVICE_HEALTH_CHANGED: 'service.health.changed' } }));

const err = (code: string) => Object.assign(new Error('服务不可用'), { code });

beforeEach(() => {
  callMock.mockReset();
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

describe('总览卡正常态', () => {
  it('UsageCard 渲染 tokens 与调用数', async () => {
    callMock.mockResolvedValue({ input_tokens: 100, output_tokens: 50, calls: 7 });
    render(<MemoryRouter><UsageCard /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('100')).toBeTruthy());
    expect(screen.getByText('50')).toBeTruthy();
    expect(screen.getByText('7')).toBeTruthy();
    expect(screen.getByText('用量 · 近 7 天')).toBeTruthy();
  });

  it('TasksCard 渲染四态计数', async () => {
    callMock.mockResolvedValue([
      { id: '1', project: 'a', status: 'running', error: '' },
      { id: '2', project: 'b', status: 'queued', error: '' },
      { id: '3', project: 'c', status: 'failed', error: 'x' },
      { id: '4', project: 'd', status: 'done', error: '' },
    ]);
    render(<MemoryRouter><TasksCard /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('索引中')).toBeTruthy());
    expect(screen.getByText('排队')).toBeTruthy();
    expect(screen.getByText('失败')).toBeTruthy();
    expect(screen.getByText('完成')).toBeTruthy();
  });

  it('SourcesCard / NotesCard 计数;NotesCard 最近 3 条', async () => {
    callMock.mockImplementation((_d: string, name: string) => {
      if (name === 'list_repos') {
        return Promise.resolve([
          { id: '1', name: 'a', status: 'ready' },
          { id: '2', name: 'b', status: 'ready' },
          { id: '3', name: 'c', status: 'importing' },
        ]);
      }
      return Promise.resolve([
        { id: 'n1', title: '第一篇', updated_ts: 4 },
        { id: 'n2', title: '第二篇', updated_ts: 3 },
        { id: 'n3', title: '第三篇', updated_ts: 2 },
        { id: 'n4', title: '第四篇', updated_ts: 1 },
      ]);
    });
    const { unmount } = render(<MemoryRouter><SourcesCard /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('2')).toBeTruthy()); // ready
    unmount();
    render(<MemoryRouter><NotesCard /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('第一篇')).toBeTruthy());
    expect(screen.queryByText('第四篇')).toBeNull(); // 只显示最近 3 条
  });

  it('ActivityCard 渲染 feed 摘要(最新在上)', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        events: [
          { seq: 1, type: 'note.created', actor: { kind: 'user', id: 'local' },
            payload: { note_id: 'n1', title: '旧' }, ts: 1 },
          { seq: 2, type: 'task.failed', actor: { kind: 'system', id: 's' },
            payload: { error: '超时' }, ts: 2 },
        ],
      }),
    });
    render(<MemoryRouter><ActivityCard /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText(/任务失败:超时/)).toBeTruthy());
    expect(screen.getByText(/创建笔记《旧》/)).toBeTruthy();
  });
});

describe('总览卡独立降级', () => {
  it('各卡错误态复用 Degraded(错误码 + 重试),互不影响', async () => {
    callMock.mockRejectedValue(err('GRAPH.UNAVAILABLE'));
    const { unmount } = render(<MemoryRouter><TasksCard /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('GRAPH.UNAVAILABLE')).toBeTruthy());
    expect(screen.getByRole('button', { name: '重试' })).toBeTruthy();
    unmount();

    callMock.mockRejectedValue(err('NOTES.DB'));
    render(<MemoryRouter><NotesCard /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('NOTES.DB')).toBeTruthy());
  });

  it('ActivityCard fetch 失败也降级', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 503 });
    render(<MemoryRouter><ActivityCard /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText(/仅此卡片降级/)).toBeTruthy());
  });
});
