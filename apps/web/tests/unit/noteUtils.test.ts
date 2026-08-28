import { describe, expect, it } from 'vitest';
import {
  applyLinePrefix,
  applyNotesListing,
  buildNoteExplainMessage,
  extractNoteToc,
  groupNotesByRecency,
  isPersistedNoteId,
  noteSnippet,
  noteSourceId,
  parseNotesFontSize,
  parseNotesLayout,
  parseNotesListState,
  parseNotesMode,
  parseNotesQuote,
  parseNotesTocWidth,
  parseSplitRatio,
  parseSyncScroll,
  sortNotes,
  startOfLocalDayMs,
  syncScrollRatio,
  tocHeadingLabel,
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

  it('首页状态默认当前', () => {
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

  it('字号夹在 12–24,缺省 15', () => {
    expect(parseNotesFontSize(null)).toBe(15);
    expect(parseNotesFontSize('')).toBe(15);
    expect(parseNotesFontSize('18')).toBe(18);
    expect(parseNotesFontSize('8')).toBe(12);
    expect(parseNotesFontSize('40')).toBe(24);
  });

  it('目录宽度夹在 148–480,缺省 188', () => {
    expect(parseNotesTocWidth(null)).toBe(188);
    expect(parseNotesTocWidth('')).toBe(188);
    expect(parseNotesTocWidth('240')).toBe(240);
    expect(parseNotesTocWidth('80')).toBe(148);
    expect(parseNotesTocWidth('900')).toBe(480);
    expect(parseNotesTocWidth('nope')).toBe(188);
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

  it('按创建时间排,置顶仍在前', () => {
    const a = { title: 'a', created_ts: 30, pinned: false };
    const b = { title: 'b', created_ts: 10, pinned: true };
    const c = { title: 'c', created_ts: 20, pinned: false };
    expect(sortNotes([a, c, b], 'created').map((n) => n.title)).toEqual(['b', 'a', 'c']);
  });
});

describe('applyNotesListing / filterNotes', () => {
  const now = Date.parse('2026-08-29T12:00:00+08:00');
  const todaySec = Math.floor((startOfLocalDayMs(now) + 8 * 3_600_000) / 1000);
  const notes = [
    { title: '新笔记', pinned: false, source_id: '', created_ts: todaySec, updated_ts: todaySec, excerpt: 'x' },
    { title: '架构', pinned: true, source_id: 'p1', created_ts: todaySec - 3_600, updated_ts: todaySec, excerpt: '设计' },
    { title: '旧文', pinned: false, source_id: 'p1', created_ts: todaySec - 800_000, updated_ts: todaySec - 800_000, excerpt: '历史' },
  ];

  it('草稿标题筛出占位名', () => {
    expect(applyNotesListing(notes, { filter: 'untitled' }).map((n) => n.title)).toEqual(['新笔记']);
  });

  it('未关联 / 置顶 / 今日', () => {
    expect(applyNotesListing(notes, { filter: 'unlinked' }).map((n) => n.title)).toEqual(['新笔记']);
    expect(applyNotesListing(notes, { filter: 'pinned' }).map((n) => n.title)).toEqual(['架构']);
    expect(applyNotesListing(notes, { filter: 'today' }, now).map((n) => n.title)).toEqual(['架构', '新笔记']);
  });

  it('关键词命中标题或摘要', () => {
    expect(applyNotesListing(notes, { query: '设计' }).map((n) => n.title)).toEqual(['架构']);
  });

  it('列表按日分段,空桶不出现', () => {
    const buckets = groupNotesByRecency(notes, 'created', now);
    expect(buckets.map((b) => b.id)).toEqual(['today', 'older']);
    expect(buckets[0].items.map((n) => n.title)).toEqual(['新笔记', '架构']);
  });
});

describe('parseNotesQuote / buildNoteExplainMessage', () => {
  it('压空白并截断', () => {
    expect(parseNotesQuote('  a \n b  ')).toBe('a b');
    expect(parseNotesQuote('x'.repeat(600)).length).toBe(500);
    expect(parseNotesQuote('   ')).toBe('');
  });

  it('解读正文带标题与人名', () => {
    const msg = buildNoteExplainMessage({ quote: 'ReAct', agentName: 'Iris', title: '架构' });
    expect(msg).toContain('Iris');
    expect(msg).toContain('快速解读');
    expect(msg).toContain('《架构》');
    expect(msg).toContain('ReAct');
  });
});

describe('extractNoteToc', () => {
  it('抽 ATX 标题并跳过围栏内的 #', () => {
    const toc = extractNoteToc('# 一级\n正文\n## 二级\n```py\n# 不是标题\n```\n### 三级');
    expect(toc.map((t) => [t.level, t.text, t.line])).toEqual([
      [1, '一级', 1],
      [2, '二级', 3],
      [3, '三级', 7],
    ]);
  });

  it('~~~ 围栏与尾部井号也对齐后端', () => {
    const toc = extractNoteToc('~~~md\n# 假\n~~~\n## 真标题 ##\n');
    expect(toc).toEqual([{ level: 2, text: '真标题', line: 4 }]);
  });

  it('底纹标记不进目录展示字', () => {
    expect(tocHeadingLabel('==warm:架构==')).toBe('架构');
    expect(tocHeadingLabel('==violet:目录==')).toBe('目录');
    expect(tocHeadingLabel('==rgb7c3aed:标题==')).toBe('标题');
    expect(tocHeadingLabel('普通')).toBe('普通');
  });
});
