/** Phase-09 单测:页面探针路由解析(resolvePageProbe 前缀,不再全等字典)
 *  与各页 provider 的摘要质量(条数/标题/selected;未就绪 null,不谎报)。 */

import { beforeEach, describe, expect, it } from 'vitest';

import { resolvePageName, resolvePageProbe } from '@/shell/pageProbes';
import { chatProvider } from '@/pages/chat/provider';
import { notesProvider, rememberNotesListCount } from '@/pages/notes/provider';
import { teamProvider, rememberTeamSnapshot } from '@/pages/team/provider';
import {
  sourceDetailProvider,
  rememberSourceDetail,
} from '@/pages/sources/provider';
import { activityProvider, rememberActivityFeedCount } from '@/pages/activity/provider';
import { useChatStore } from '@/stores/chatStore';
import { useNoteStore } from '@/stores/noteStore';

beforeEach(() => {
  // 各页 module cache 是跨测试的模块级状态:每个用例前归零
  rememberNotesListCount(null);
  rememberTeamSnapshot(null);
  rememberSourceDetail(null);
  rememberActivityFeedCount(null);
  useChatStore.setState({ messages: [] });
  useNoteStore.setState({ editingNoteId: null, editorTitle: '', editorContent: '' });
});

describe('resolvePageProbe 路由解析', () => {
  it('领域页与前缀路径都解析到正确的 probe', () => {
    expect(resolvePageProbe('/')?.page).toBe('chat');
    expect(resolvePageProbe('/chat')?.page).toBe('chat');
    expect(resolvePageProbe('/chat/abc')?.page).toBe('chat');
    expect(resolvePageProbe('/notes')?.page).toBe('notes');
    expect(resolvePageProbe('/notes/')?.page).toBe('notes');
    // 任务书指定:详情路由落到 sources
    expect(resolvePageProbe('/sources/repo/abc')?.page).toBe('sources');
    expect(resolvePageProbe('/sources/doc/abc')?.page).toBe('sources');
    expect(resolvePageProbe('/graph')?.page).toBe('graph');
    expect(resolvePageProbe('/graph/sub')?.page).toBe('graph');
    expect(resolvePageProbe('/code-graph')?.page).toBe('graph');
    expect(resolvePageProbe('/code-graph/proj-1')?.page).toBe('graph');
    expect(resolvePageProbe('/team')?.page).toBe('team');
    expect(resolvePageProbe('/activity')?.page).toBe('activity');
  });

  it('settings / usage / health / overview 不注册 provider(不上报)', () => {
    expect(resolvePageName('/settings')).toBeNull();
    expect(resolvePageName('/usage')).toBeNull();
    expect(resolvePageName('/system/health')).toBeNull();
    expect(resolvePageName('/overview')).toBeNull();
    expect(resolvePageProbe('/settings')).toBeNull();
  });
});

describe('notes provider 摘要质量', () => {
  it('列表 cache 写入后摘要含条数与《标题》,counts.notes 正确,不含正文', () => {
    rememberNotesListCount(36);
    useNoteStore.setState({
      editingNoteId: 'n-1',
      editorTitle: 'langgraph 笔记',
      editorContent: '这是不该出现在摘要里的正文内容。',
    });
    const out = notesProvider.report();
    expect(out).not.toBeNull();
    expect(out?.summary).toContain('36 条笔记');
    expect(out?.summary).toContain('《langgraph 笔记》');
    expect(out?.counts).toMatchObject({ notes: 36 });
    expect(out?.selected).toBe('n-1');
    // editorContent 不准进 summary
    expect(out?.summary).not.toContain('不该出现在摘要里');
  });

  it('列表从未到达(cache 为 null)不谎报 0 条', () => {
    const out = notesProvider.report();
    expect(out).not.toBeNull();
    expect(out?.summary).not.toContain('0 条笔记');
    expect(out?.counts).toBeUndefined();
  });

  it('空列表(0 条)是真实状态,照报', () => {
    rememberNotesListCount(0);
    const out = notesProvider.report();
    expect(out?.summary).toContain('0 条笔记');
    expect(out?.counts).toMatchObject({ notes: 0 });
  });
});

describe('team provider 摘要质量', () => {
  it('未加载(无快照)返回 null,不报 0 个人格', () => {
    expect(teamProvider.report()).toBeNull();
  });

  it('快照写入后报人格/自建/运行中计数', () => {
    rememberTeamSnapshot({ personas: 5, definitions: 2, running: 1 });
    const out = teamProvider.report();
    expect(out?.summary).toBe('团队 · 5 个人格 · 2 个自建 · 1 个运行中');
    expect(out?.counts).toMatchObject({ personas: 5, definitions: 2, running: 1 });
  });
});

describe('sources provider 摘要质量', () => {
  it('详情页:标题未到用 id,标题到了用标题;selected 是 id', () => {
    rememberSourceDetail({ kind: 'repo', id: 'abc-123', title: '' });
    let out = sourceDetailProvider.report();
    expect(out?.summary).toBe('资源详情 · 仓库 · abc-123');
    expect(out?.selected).toBe('abc-123');

    rememberSourceDetail({ kind: 'repo', id: 'abc-123', title: 'voyager/后端' });
    out = sourceDetailProvider.report();
    expect(out?.summary).toBe('资源详情 · 仓库 · voyager/后端');
  });

  it('详情摘要不带 README/正文类长文', () => {
    rememberSourceDetail({ kind: 'doc', id: 'd-1', title: '一份很长的文档标题'.repeat(10) });
    const out = sourceDetailProvider.report();
    expect((out?.summary ?? '').length).toBeLessThan(80);
  });
});

describe('chat / activity provider', () => {
  it('chat:0 条也报(空对话是真实状态)', () => {
    const out = chatProvider.report();
    expect(out?.summary).toBe('对话 · 0 条消息');
    expect(out?.counts).toMatchObject({ messages: 0 });
  });

  it('chat:按消息条数报', () => {
    useChatStore.setState({
      messages: [
        { seq: 1, role: 'user', content: 'a' },
        { seq: 2, role: 'agent', content: 'b' },
      ],
    });
    expect(chatProvider.report()?.summary).toBe('对话 · 2 条消息');
  });

  it('activity:未加载 null;拉到后报条数', () => {
    expect(activityProvider.report()).toBeNull();
    rememberActivityFeedCount(7);
    expect(activityProvider.report()?.summary).toBe('活动 · 7 条');
    expect(activityProvider.report()?.counts).toMatchObject({ events: 7 });
  });
});
