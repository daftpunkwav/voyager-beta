import { describe, expect, it } from 'vitest';
import {
  applyLinePrefix,
  isPersistedNoteId,
  noteSnippet,
  noteSourceId,
  parseNotesFontSize,
  parseNotesLayout,
  parseNotesListState,
  parseNotesMode,
  parseSplitRatio,
  parseSyncScroll,
  sortNotes,
  syncScrollRatio,
} from '@/pages/notes/noteUtils';

describe('parseNotesMode', () => {
  it('只认 notes-mode,缺省为编辑', () => {
    expect(parseNotesMode('edit')).toBe('edit');
    expect(parseNotesMode('preview')).toBe('preview');
    expect(parseNotesMode('split')).toBe('split');
    expect(parseNotesMode(null)).toBe('edit');
    expect(parseNotesMode('nope')).toBe('edit');
  });
});

describe('parseNotesLayout / parseSplitRatio / parseNotesListState', () => {
  it('布局默认列表,卡片显式开启', () => {
    expect(parseNotesLayout('card')).toBe('card');
    expect(parseNotesLayout('list')).toBe('list');
    expect(parseNotesLayout(null)).toBe('list');
  });

  it('首页状态默认在用', () => {
    expect(parseNotesListState('archived')).toBe('archived');
    expect(parseNotesListState('active')).toBe('active');
    expect(parseNotesListState(null)).toBe('active');
  });

  it('分栏比例夹在 0.32–0.72', () => {
    expect(parseSplitRatio('0.55')).toBe(0.55);
    expect(parseSplitRatio('0.1')).toBe(0.32);
    expect(parseSplitRatio('0.99')).toBe(0.72);
    expect(parseSplitRatio('nope')).toBe(0.55);
  });

  it('字号夹在 13–20,缺省 15', () => {
    expect(parseNotesFontSize(null)).toBe(15);
    expect(parseNotesFontSize('')).toBe(15);
    expect(parseNotesFontSize('18')).toBe(18);
    expect(parseNotesFontSize('8')).toBe(13);
    expect(parseNotesFontSize('40')).toBe(20);
  });

  it('同步滚动缺省开启,仅 0 关闭', () => {
    expect(parseSyncScroll(null)).toBe(true);
    expect(parseSyncScroll('1')).toBe(true);
    expect(parseSyncScroll('0')).toBe(false);
  });
});

describe('syncScrollRatio', () => {
  it('按可滚动比例同步,零高度跳过', () => {
    const from = { scrollHeight: 200, clientHeight: 100, scrollTop: 50 } as HTMLElement;
    const to = { scrollHeight: 400, clientHeight: 100, scrollTop: 0 } as HTMLElement;
    syncScrollRatio(from, to);
    expect(to.scrollTop).toBe(150);
    const stuck = { scrollHeight: 80, clientHeight: 100, scrollTop: 0 } as HTMLElement;
    const dest = { scrollHeight: 400, clientHeight: 100, scrollTop: 9 } as HTMLElement;
    syncScrollRatio(stuck, dest);
    expect(dest.scrollTop).toBe(9);
  });
});

describe('isPersistedNoteId', () => {
  it('new / 空不是已落盘笔记', () => {
    expect(isPersistedNoteId('new')).toBe(false);
    expect(isPersistedNoteId(null)).toBe(false);
    expect(isPersistedNoteId('')).toBe(false);
    expect(isPersistedNoteId('n_abc')).toBe(true);
  });
});

describe('noteSourceId / noteSnippet', () => {
  it('兼容 project_id 与 source_id', () => {
    expect(noteSourceId({ source_id: 's1' })).toBe('s1');
    expect(noteSourceId({ project_id: 'p1' })).toBe('p1');
    expect(noteSourceId({ project_id: 'p1', source_id: 's1' })).toBe('p1');
    expect(noteSourceId({})).toBe('');
  });

  it('列表摘要优先 excerpt,去掉 markdown 标记', () => {
    expect(noteSnippet({ excerpt: '# 标题 摘要', content: '全文不应出现' })).toBe('标题 摘要');
    expect(noteSnippet({ content: '**粗** 体' })).toBe('粗 体');
    expect(noteSnippet({})).toBe('');
  });
});

describe('applyLinePrefix', () => {
  it('套上标题/引用/列表前缀,再点一次去掉', () => {
    expect(applyLinePrefix('hello', '## ')).toBe('## hello');
    expect(applyLinePrefix('## hello', '## ')).toBe('hello');
    expect(applyLinePrefix('hello', '> ')).toBe('> hello');
    expect(applyLinePrefix('> hello', '> ')).toBe('hello');
    expect(applyLinePrefix('# old', '## ')).toBe('## old');
  });

  it('短前缀 - 不误吞任务列表', () => {
    expect(applyLinePrefix('- [ ] task', '- ')).toBe('- task');
    expect(applyLinePrefix('- item', '- ')).toBe('item');
    expect(applyLinePrefix('plain', '- [ ] ')).toBe('- [ ] plain');
    expect(applyLinePrefix('- [ ] plain', '- [ ] ')).toBe('plain');
  });
});

describe('sortNotes', () => {
  const a = { title: 'Beta', pinned: false, updated_ts: 100 };
  const b = { title: 'Alpha', pinned: true, updated_ts: 50 };
  const c = { title: 'Gamma', pinned: false, updated_ts: 200 };

  it('置顶始终在前,其余按最近更新', () => {
    expect(sortNotes([a, b, c], 'updated').map((n) => n.title)).toEqual(['Alpha', 'Gamma', 'Beta']);
  });

  it('置顶始终在前,其余按标题', () => {
    expect(sortNotes([c, a, b], 'title').map((n) => n.title)).toEqual(['Alpha', 'Beta', 'Gamma']);
  });

  it('秒级 updated_ts 与 ISO updated_at 可比较', () => {
    const older = { title: 'old', updated_ts: 1_700_000_000 };
    const newer = { title: 'new', updated_at: '2026-08-28T00:00:00.000Z' };
    expect(sortNotes([older, newer], 'updated').map((n) => n.title)).toEqual(['new', 'old']);
  });
});
