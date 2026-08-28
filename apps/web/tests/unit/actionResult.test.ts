import { describe, expect, it } from 'vitest';
import { parseActionResult } from '@/utils/actionResult';
import { routes } from '@/utils/routes';

describe('parseActionResult 链接闸门', () => {
  it('兼容旧 session 绑定标记并指向资源库', () => {
    const view = parseActionResult({ __session_projects__: true, count: 2, project_ids: ['a', 'b'] });
    expect(view?.links).toEqual([{ label: '资源库', href: routes.sources }]);
  });

  it('丢弃 javascript / 协议相对 / 外链,只留站内路径', () => {
    const view = parseActionResult({
      __action__: 'note_created',
      summary: 'ok',
      links: [
        { label: '笔记', href: '/notes?note=n1' },
        { label: 'xss', href: 'javascript:alert(1)' },
        { label: 'phish', href: '//evil.example/x' },
        { label: '外链', href: 'https://evil.example/' },
      ],
    });
    expect(view?.links).toEqual([{ label: '笔记', href: '/notes?note=n1' }]);
  });
});
