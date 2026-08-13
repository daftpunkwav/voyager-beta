import { describe, expect, it } from 'vitest';
import {
  actionSummaryFromToolResult,
  parseActionResult,
} from '@/utils/actionResult';

describe('parseActionResult', () => {
  it('解析 note_created', () => {
    const view = parseActionResult({
      __action__: 'note_created',
      ok: true,
      summary: '已创建笔记《A》',
      resource: { type: 'note', id: '1', title: 'A', project_name: 'demo' },
      links: [{ label: '打开笔记', href: '/notes?note=1' }],
    });
    expect(view).not.toBeNull();
    expect(view!.kind).toBe('note');
    expect(view!.links[0].href).toContain('/notes');
  });

  it('解析 tags_applied', () => {
    const view = parseActionResult({
      __action__: 'tags_applied',
      ok: true,
      summary: '已设置标签',
      resource: {
        type: 'project',
        name: 'p',
        tags: [{ id: '1', name: '引擎' }],
      },
      links: [],
    });
    expect(view!.kind).toBe('tags');
  });

  it('兼容 session_projects 旧标记', () => {
    const view = parseActionResult({
      __session_projects__: true,
      ok: true,
      count: 2,
      project_ids: ['a', 'b'],
    });
    expect(view!.kind).toBe('session');
    expect(view!.summary).toContain('2');
  });

  it('非动作结果返回 null', () => {
    expect(parseActionResult({ projects: [] })).toBeNull();
    expect(parseActionResult(null)).toBeNull();
  });
});

describe('actionSummaryFromToolResult', () => {
  it('提取摘要', () => {
    expect(
      actionSummaryFromToolResult({
        __action__: 'progress_updated',
        summary: '已改为已掌握',
        ok: true,
      })
    ).toBe('已改为已掌握');
  });
});
