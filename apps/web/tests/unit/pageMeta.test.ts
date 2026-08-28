import { describe, expect, it } from 'vitest';
import { resolvePageTitle } from '@/shell/pageMeta';

describe('resolvePageTitle', () => {
  it('一级页与详情页都给出栏目名', () => {
    expect(resolvePageTitle('/')).toBe('对话');
    expect(resolvePageTitle('/chat/abc')).toBe('对话');
    expect(resolvePageTitle('/team')).toBe('团队');
    expect(resolvePageTitle('/notes')).toBe('笔记');
    expect(resolvePageTitle('/sources')).toBe('资源库');
    expect(resolvePageTitle('/sources/repo/x')).toBe('资源库');
    expect(resolvePageTitle('/graph')).toBe('图谱');
    expect(resolvePageTitle('/code-graph/x')).toBe('图谱');
    expect(resolvePageTitle('/overview')).toBe('总览');
    expect(resolvePageTitle('/activity')).toBe('活动');
    expect(resolvePageTitle('/system/health')).toBe('服务状态');
    expect(resolvePageTitle('/usage')).toBe('用量');
    expect(resolvePageTitle('/settings')).toBe('设置');
  });

  it('未知路径不编造标题', () => {
    expect(resolvePageTitle('/no-such')).toBe('');
  });
});
